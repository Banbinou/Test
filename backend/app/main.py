from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable
from uuid import uuid4

import pandas as pd
import pm4py
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator


app = FastAPI(title="Process Mining API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


UPLOADS: dict[str, Path] = {}
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}
SUPPORTED_ANALYSES = {"discovery", "statistics", "variants"}
DEFAULT_ANALYSES = ["discovery", "statistics", "variants"]


class MappingConfig(BaseModel):
    case_id: str = Field(..., description="Column mapped to case identifier")
    activity: str = Field(..., description="Column mapped to activity")
    timestamp: str = Field(..., description="Column mapped to timestamp")
    resource: str | None = Field(None, description="Optional resource column")


class AnalysisRequest(BaseModel):
    file_id: str
    mapping: MappingConfig
    analyses: list[str] = Field(default_factory=lambda: DEFAULT_ANALYSES.copy())

    @field_validator("analyses")
    @classmethod
    def validate_analyses(cls, analyses: list[str]) -> list[str]:
        if not analyses:
            raise ValueError("At least one analysis must be selected")
        unknown = sorted(set(analyses) - SUPPORTED_ANALYSES)
        if unknown:
            raise ValueError(f"Unsupported analyses: {unknown}")
        return list(dict.fromkeys(analyses))


def _load_preview(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, low_memory=True, nrows=20)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, nrows=20)
    raise HTTPException(status_code=400, detail="Format de fichier non supporté")


def _selected_columns(mapping: MappingConfig) -> list[str]:
    columns = [mapping.case_id, mapping.activity, mapping.timestamp]
    if mapping.resource:
        columns.append(mapping.resource)
    return list(dict.fromkeys(columns))


def _load_dataframe_for_analysis(path: Path, selected_columns: Iterable[str]) -> pd.DataFrame:
    suffix = path.suffix.lower()
    usecols = list(selected_columns)

    if suffix == ".csv":
        return pd.read_csv(path, low_memory=True, usecols=usecols)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, usecols=usecols)

    raise HTTPException(status_code=400, detail="Format de fichier non supporté")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> dict[str, Any]:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Seulement CSV/XLSX/XLS sont supportés")

    with NamedTemporaryFile(delete=False, suffix=extension) as tmp_file:
        tmp_file.write(await file.read())
        temp_path = Path(tmp_file.name)

    file_id = str(uuid4())
    UPLOADS[file_id] = temp_path

    try:
        sample_df = _load_preview(temp_path)
    except Exception as exc:  # pragma: no cover - depends on user files
        temp_path.unlink(missing_ok=True)
        UPLOADS.pop(file_id, None)
        raise HTTPException(status_code=400, detail=f"Lecture de fichier impossible: {exc}") from exc

    return {
        "file_id": file_id,
        "columns": sample_df.columns.tolist(),
        "preview": sample_df.fillna("").to_dict(orient="records"),
    }


@app.post("/analyze")
def analyze(request: AnalysisRequest) -> dict[str, Any]:
    path = UPLOADS.get(request.file_id)
    if not path or not path.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable")

    required_columns = _selected_columns(request.mapping)

    try:
        df = _load_dataframe_for_analysis(path, required_columns)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Colonnes invalides pour ce fichier: {exc}") from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=400, detail=f"Impossible de lire les données: {exc}") from exc

    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise HTTPException(status_code=400, detail=f"Colonnes manquantes: {missing}")

    dataframe = df.copy()
    dataframe[request.mapping.timestamp] = pd.to_datetime(
        dataframe[request.mapping.timestamp],
        errors="coerce",
        utc=True,
    )
    dataframe = dataframe.dropna(subset=[request.mapping.case_id, request.mapping.activity, request.mapping.timestamp])

    if dataframe.empty:
        raise HTTPException(
            status_code=400,
            detail="Aucun événement valide après normalisation des colonnes case_id/activity/timestamp",
        )

    event_log = pm4py.format_dataframe(
        dataframe,
        case_id=request.mapping.case_id,
        activity_key=request.mapping.activity,
        timestamp_key=request.mapping.timestamp,
    )

    result: dict[str, Any] = {"events": int(len(event_log))}

    if "discovery" in request.analyses:
        dfg, start_activities, end_activities = pm4py.discover_dfg(event_log)
        top_edges = sorted(dfg.items(), key=lambda edge: edge[1], reverse=True)[:15]
        result["discovery"] = {
            "start_activities": start_activities,
            "end_activities": end_activities,
            "top_edges": [
                {"from": source, "to": target, "count": count}
                for (source, target), count in top_edges
            ],
        }

    if "statistics" in request.analyses:
        grouped = event_log.groupby(request.mapping.case_id)[request.mapping.timestamp]
        case_durations = (grouped.max() - grouped.min()).dt.total_seconds()
        result["statistics"] = {
            "cases": int(event_log[request.mapping.case_id].nunique()),
            "activities": int(event_log[request.mapping.activity].nunique()),
            "duration_seconds": {
                "mean": float(case_durations.mean()) if not case_durations.empty else 0,
                "median": float(case_durations.median()) if not case_durations.empty else 0,
                "p95": float(case_durations.quantile(0.95)) if not case_durations.empty else 0,
            },
        }

    if "variants" in request.analyses:
        variants = pm4py.get_variants_as_tuples(event_log)
        sorted_variants = sorted(variants.items(), key=lambda item: len(item[1]), reverse=True)
        result["variants"] = [
            {
                "variant": " > ".join(variant),
                "cases": len(cases),
            }
            for variant, cases in sorted_variants[:20]
        ]

    return result
