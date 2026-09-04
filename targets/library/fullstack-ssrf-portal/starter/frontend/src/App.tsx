import React, { useState, useEffect } from 'react'

export default function App() {
  const [url, setUrl] = useState('')
  const [result, setResult] = useState<string | null>(null)
  const [logs, setLogs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const fetchLogs = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8000/api/webhooks/logs')
      const data = await res.json()
      setLogs(data.logs || [])
    } catch (e) {
      console.error(e)
    }
  }

  useEffect(() => {
    fetchLogs()
  }, [])

  const handleTest = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResult(null)
    try {
      const res = await fetch('http://127.0.0.1:8000/api/webhooks/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      })
      const data = await res.json()
      setResult(JSON.stringify(data, null, 2))
      fetchLogs()
    } catch (err: any) {
      setResult(`Error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif', maxWidth: 800, margin: '0 auto' }}>
      <h1>Webhook Relay & SSRF Portal</h1>
      <form onSubmit={handleTest} style={{ marginBottom: '2rem' }}>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <input
            type="text"
            id="webhook-url-input"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/webhook"
            style={{ flex: 1, padding: '0.5rem', fontSize: '1rem' }}
            required
          />
          <button id="webhook-test-submit" type="submit" disabled={loading} style={{ padding: '0.5rem 1rem' }}>
            {loading ? 'Pinging...' : 'Test Webhook'}
          </button>
        </div>
      </form>

      {result && (
        <div style={{ marginBottom: '2rem' }}>
          <h3>Dispatch Result</h3>
          <pre id="webhook-result" style={{ background: '#f4f4f4', padding: '1rem', borderRadius: 4 }}>{result}</pre>
        </div>
      )}

      <div>
        <h3>Recent Dispatch History</h3>
        {logs.length === 0 ? (
          <p>No dispatches recorded.</p>
        ) : (
          <ul>
            {logs.map((log, idx) => (
              <li key={idx}><strong>{log.url}</strong> - Status: {log.status_code}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
