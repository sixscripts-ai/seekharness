import React, { useState } from 'react'

export default function App() {
  const [token, setToken] = useState<string | null>(null)
  const [profile, setProfile] = useState<any>(null)
  const [statusMsg, setStatusMsg] = useState<string>('')

  const handleSimulateLogin = async () => {
    setStatusMsg('Requesting authorization code...')
    try {
      // 1. Authorize
      const authRes = await fetch('http://127.0.0.1:8000/oauth/authorize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: 'client_webapp',
          code_challenge: 'E9Melhoa2OwvFrGMTJguCH5rtx6441C8E_08C61mqAw',
          code_challenge_method: 'S256'
        })
      })
      const authData = await authRes.json()
      const code = authData.authorization_code

      // 2. Token Exchange
      setStatusMsg('Exchanging code for token...')
      const tokenRes = await fetch('http://127.0.0.1:8000/oauth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_id: 'client_webapp',
          code: code,
          code_verifier: 'dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'
        })
      })
      const tokenData = await tokenRes.json()
      setToken(tokenData.access_token)
      setStatusMsg('Logged in successfully!')

      // 3. Fetch Profile
      const profRes = await fetch('http://127.0.0.1:8000/api/profile', {
        headers: { 'Authorization': `Bearer ${tokenData.access_token}` }
      })
      const profData = await profRes.json()
      setProfile(profData)
    } catch (e: any) {
      setStatusMsg(`Authentication failed: ${e.message}`)
    }
  }

  const handleLogout = async () => {
    if (!token) return
    try {
      await fetch('http://127.0.0.1:8000/api/logout', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      setToken(null)
      setProfile(null)
      setStatusMsg('Logged out. Session revoked.')
    } catch (e: any) {
      setStatusMsg(`Logout failed: ${e.message}`)
    }
  }

  return (
    <div style={{ padding: '2rem', fontFamily: 'sans-serif', maxWidth: 800, margin: '0 auto' }}>
      <h1>OAuth SSO & Session Replay Defense Portal</h1>
      <p style={{ color: '#666' }}>Status: {statusMsg || 'Idle'}</p>

      {!token ? (
        <button id="oauth-login-btn" onClick={handleSimulateLogin} style={{ padding: '0.75rem 1.5rem', fontSize: '1rem' }}>
          Simulate OAuth Login (PKCE Flow)
        </button>
      ) : (
        <div>
          <button id="oauth-logout-btn" onClick={handleLogout} style={{ padding: '0.5rem 1rem', marginBottom: '1.5rem' }}>
            Logout & Revoke Token
          </button>
          <div style={{ background: '#f8f8f8', padding: '1rem', borderRadius: 4 }}>
            <h3>User Profile</h3>
            <pre id="oauth-profile">{JSON.stringify(profile, null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  )
}
