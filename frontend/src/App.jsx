import { useMemo, useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

const analysisLabels = {
  discovery: 'Process discovery',
  statistics: 'Statistiques',
  variants: 'Variants',
}

function ErrorBox({ message }) {
  if (!message) return null
  return <p className="error">{message}</p>
}

function App() {
  const [file, setFile] = useState(null)
  const [fileId, setFileId] = useState('')
  const [columns, setColumns] = useState([])
  const [preview, setPreview] = useState([])
  const [mapping, setMapping] = useState({ case_id: '', activity: '', timestamp: '', resource: '' })
  const [analyses, setAnalyses] = useState(['discovery', 'statistics', 'variants'])
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const canAnalyze = useMemo(
    () => fileId && mapping.case_id && mapping.activity && mapping.timestamp && analyses.length > 0,
    [fileId, mapping, analyses],
  )

  const parseError = async (response) => {
    const text = await response.text()
    try {
      const parsed = JSON.parse(text)
      return parsed.detail ?? text
    } catch {
      return text
    }
  }

  const onUpload = async (event) => {
    event.preventDefault()
    if (!file) return

    const formData = new FormData()
    formData.append('file', file)

    setError('')
    setResult(null)
    setLoading(true)

    try {
      const response = await fetch(`${API_URL}/upload`, { method: 'POST', body: formData })
      if (!response.ok) throw new Error(await parseError(response))

      const data = await response.json()
      setFileId(data.file_id)
      setColumns(data.columns)
      setPreview(data.preview)
      setMapping((prev) => ({
        case_id: prev.case_id || data.columns[0] || '',
        activity: prev.activity || data.columns[1] || '',
        timestamp: prev.timestamp || data.columns[2] || '',
        resource: prev.resource || '',
      }))
    } catch (uploadError) {
      setError(`Upload impossible: ${uploadError.message}`)
    } finally {
      setLoading(false)
    }
  }

  const runAnalysis = async () => {
    setError('')
    setResult(null)
    setLoading(true)

    try {
      const response = await fetch(`${API_URL}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_id: fileId, mapping, analyses }),
      })
      if (!response.ok) throw new Error(await parseError(response))

      setResult(await response.json())
    } catch (analysisError) {
      setError(`Analyse impossible: ${analysisError.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="container">
      <h1>Process Mining Studio</h1>
      <p className="subtitle">
        Importez un fichier CSV/XLSX volumineux, mappez les colonnes PM4Py, puis lancez les analyses.
      </p>

      <section className="card">
        <h2>1) Import</h2>
        <form onSubmit={onUpload} className="upload-row">
          <input type="file" accept=".csv,.xlsx,.xls" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          <button type="submit" disabled={!file || loading}>{loading ? 'Chargement…' : 'Uploader'}</button>
        </form>
        {fileId && <p className="success">Fichier chargé (id: {fileId})</p>}
      </section>

      <section className="card">
        <h2>2) Mapping des colonnes PM4Py</h2>
        {columns.length === 0 ? (
          <p>Chargez un fichier pour afficher les colonnes.</p>
        ) : (
          <div className="grid">
            {[
              ['case_id', 'Case ID'],
              ['activity', 'Activité'],
              ['timestamp', 'Timestamp'],
              ['resource', 'Ressource (optionnel)'],
            ].map(([key, label]) => (
              <label key={key}>
                {label}
                <select value={mapping[key]} onChange={(e) => setMapping((prev) => ({ ...prev, [key]: e.target.value }))}>
                  <option value="">-- sélectionner --</option>
                  {columns.map((column) => (
                    <option key={column} value={column}>
                      {column}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <h2>3) Analyses</h2>
        <div className="checks">
          {Object.entries(analysisLabels).map(([key, label]) => (
            <label key={key} className="check-item">
              <input
                type="checkbox"
                checked={analyses.includes(key)}
                onChange={(e) =>
                  setAnalyses((current) =>
                    e.target.checked ? [...current, key] : current.filter((entry) => entry !== key),
                  )
                }
              />
              {label}
            </label>
          ))}
        </div>
        <button onClick={runAnalysis} disabled={!canAnalyze || loading}>
          {loading ? 'Analyse en cours…' : "Lancer l'analyse"}
        </button>
      </section>

      {preview.length > 0 && (
        <section className="card">
          <h2>Aperçu des données (20 lignes max)</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {Object.keys(preview[0]).map((column) => (
                    <th key={column}>{column}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.map((row, index) => (
                  <tr key={index}>
                    {Object.entries(row).map(([key, value]) => (
                      <td key={key}>{String(value)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <ErrorBox message={error} />

      {result && (
        <section className="card">
          <h2>Résultats</h2>
          <div className="result-grid">
            {'statistics' in result && (
              <article className="result-card">
                <h3>Statistiques</h3>
                <p>Cas: {result.statistics.cases}</p>
                <p>Activités: {result.statistics.activities}</p>
                <p>Durée moyenne (s): {Math.round(result.statistics.duration_seconds.mean)}</p>
              </article>
            )}
            {'variants' in result && (
              <article className="result-card">
                <h3>Top variants</h3>
                <ol>
                  {result.variants.slice(0, 5).map((entry) => (
                    <li key={entry.variant}>{entry.variant} ({entry.cases})</li>
                  ))}
                </ol>
              </article>
            )}
          </div>
          <details>
            <summary>JSON complet</summary>
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </details>
        </section>
      )}
    </main>
  )
}

export default App
