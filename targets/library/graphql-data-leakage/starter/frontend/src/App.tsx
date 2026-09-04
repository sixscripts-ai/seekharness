import React, { useState } from 'react'

export default function App() {
  const [query, setQuery] = useState('query { me { id name email } }')
  const [response, setResponse] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleExecute = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)
    setResponse(null)
    try {
      const res = await fetch('http://127.0.0.1:8000/graphql', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query })
      })
      const data = await res.json()
      setResponse(JSON.stringify(data, null, 2))
    } catch (err: any) {
      setResponse(`Network error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif', maxWidth: 800, margin: '0 auto' }}>
      <h1>Customer Intelligence GraphQL Portal</h1>
      <form onSubmit={handleExecute} style={{ marginBottom: '1.5rem' }}>
        <textarea
          id="graphql-query-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={6}
          style={{ width: '100%', fontFamily: 'monospace', padding: '0.5rem', marginBottom: '0.5rem' }}
          required
        />
        <button id="graphql-submit" type="submit" disabled={loading} style={{ padding: '0.5rem 1.5rem' }}>
          {loading ? 'Executing...' : 'Run Query'}
        </button>
      </form>

      {response && (
        <div>
          <h3>GraphQL Response</h3>
          <pre id="graphql-result" style={{ background: '#1e1e1e', color: '#00ffcc', padding: '1rem', borderRadius: 4, overflowX: 'auto' }}>
            {response}
          </pre>
        </div>
      )}
    </div>
  )
}
