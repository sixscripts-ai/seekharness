import React, { useState } from 'react';

export function App() {
  const [balance, setBalance] = useState<number>(100000.0);
  const [recipient, setRecipient] = useState('');
  const [amount, setAmount] = useState('');
  const [status, setStatus] = useState('READY');

  const handleTransfer = (e: React.FormEvent) => {
    e.preventDefault();
    const val = parseFloat(amount);
    if (isNaN(val) || val <= 0 || val > balance) {
      setStatus('TRANSFER_FAILED');
      return;
    }
    setBalance((prev) => prev - val);
    setStatus(`TRANSFERRED_${val}_TO_${recipient}`);
  };

  return (
    <div className="vault-container" style={{ padding: 24, fontFamily: 'sans-serif' }}>
      <h1>Bank Vault Portal</h1>
      <div id="status-banner">{status}</div>
      <div id="vault-balance">Balance: ${balance.toLocaleString()}</div>
      <form onSubmit={handleTransfer} style={{ marginTop: 16 }}>
        <input
          id="recipient-input"
          placeholder="Recipient"
          value={recipient}
          onChange={(e) => setRecipient(e.target.value)}
        />
        <input
          id="amount-input"
          placeholder="Amount"
          type="number"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
        />
        <button id="transfer-button" type="submit">Transfer</button>
      </form>
    </div>
  );
}

export default App;
