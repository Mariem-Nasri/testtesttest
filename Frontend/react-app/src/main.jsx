import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import App from './App.jsx'
import './index.css'

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <BrowserRouter>
      {/* Global toast notifications */}
      <Toaster
        position="bottom-right"
        toastOptions={{
          duration: 4000,
          style: {
            fontFamily: 'Inter, sans-serif',
            fontSize: '14px',
            borderRadius: '10px',
          },
          success: { iconTheme: { primary: '#00a76f', secondary: '#fff' } },
          error:   { iconTheme: { primary: '#e74c3c',  secondary: '#fff' } },
        }}
      />
      <App />
    </BrowserRouter>
  </React.StrictMode>
)
