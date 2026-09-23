import { useState, useRef, useEffect, useCallback } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import Login from './pages/Login'
import Signup from './pages/Signup'
import './App.css'

const API = '/api'

const EXAMPLES = [
  "What is diabetes?",
  "What are the symptoms of diabetes?",
  "What causes hypertension?",
  "What are the symptoms of anemia?",
  "What is asthma?",
  "What is pneumonia?"
]

function App() {
  // Auth state
  const [page, setPage] = useState('login') // login | signup | chat
  const [token, setToken] = useState(null)
  const [user, setUser] = useState(null)

  // Theme
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'light')

  // Chat state
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(() => typeof window !== 'undefined' ? window.innerWidth > 800 : true)
  const [sidebarWidth, setSidebarWidth] = useState(() => {
    try {
      const saved = localStorage.getItem('sidebar_width')
      return saved ? parseInt(saved, 10) : 260
    } catch {
      return 260
    }
  })
  const [isResizing, setIsResizing] = useState(false)

  const startResizing = useCallback((e) => {
    e.preventDefault()
    setIsResizing(true)
  }, [])

  useEffect(() => {
    const handleMouseMove = (e) => {
      if (!isResizing) return
      const newWidth = Math.min(Math.max(e.clientX, 190), 460)
      setSidebarWidth(newWidth)
      try {
        localStorage.setItem('sidebar_width', newWidth.toString())
      } catch {}
    }
    const handleMouseUp = () => {
      setIsResizing(false)
    }
    if (isResizing) {
      window.addEventListener('mousemove', handleMouseMove)
      window.addEventListener('mouseup', handleMouseUp)
    }
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [isResizing])

  const [copiedIdx, setCopiedIdx] = useState(null)

  // History state
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)

  // Share state
  const [shareModal, setShareModal] = useState({ open: false, url: '', copied: false, loading: false, error: '' })
  const [sharedSession, setSharedSession] = useState(null)

  // Change Password Modal state
  const [showPasswordModal, setShowPasswordModal] = useState(false)
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [passwordMsg, setPasswordMsg] = useState({ type: '', text: '' })
  const [isChangingPw, setIsChangingPw] = useState(false)

  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)
  const abortControllerRef = useRef(null)

  // ---- Check for shared chat in URL on mount ----
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const shareToken = params.get('share')
    if (shareToken) {
      setPage('shared')
      fetch(`${API}/share/${shareToken}`)
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(data => {
          if (data.session) setSharedSession(data.session)
        })
        .catch(() => {
          setSharedSession({ error: 'This shared consultation could not be found or has expired.' })
        })
    }
  }, [])

  // ---- Theme management ----
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme(prev => prev === 'dark' ? 'light' : 'dark')
  }

  // ---- Auth: check saved token on mount ----
  useEffect(() => {
    const savedToken = localStorage.getItem('token')
    if (savedToken) {
      fetch(`${API}/auth/me`, {
        headers: { 'Authorization': `Bearer ${savedToken}` }
      })
        .then(r => r.ok ? r.json() : Promise.reject())
        .then(data => {
          setToken(savedToken)
          setUser(data.user)
          setPage('chat')
        })
        .catch(() => {
          localStorage.removeItem('token')
        })
    }
  }, [])

  // ---- Load history when authenticated ----
  const loadHistory = useCallback(() => {
    if (!token) return
    fetch(`${API}/history`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => setSessions(data.sessions || []))
      .catch(() => {})
  }, [token])

  useEffect(() => {
    if (page === 'chat' && token) loadHistory()
  }, [page, token, loadHistory])

  // ---- Auth handlers ----
  const handleAuth = (newToken, newUser) => {
    setToken(newToken)
    setUser(newUser)
    localStorage.setItem('token', newToken)
    setPage('chat')
  }

  const handleLogout = () => {
    setToken(null)
    setUser(null)
    setMessages([])
    setActiveSessionId(null)
    setSessions([])
    localStorage.removeItem('token')
    setPage('login')
  }

  // ---- Scroll ----
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  useEffect(() => {
    if (page === 'chat') {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [page, activeSessionId])

  // ---- Save session ----
  const saveSession = useCallback(async (msgs, sessionId, customTitle = null) => {
    if (!token || msgs.length === 0) return sessionId

    let title = customTitle
    if (!title) {
      const firstUserMsg = msgs.find(m => m.role === 'user')
      title = firstUserMsg
        ? firstUserMsg.content.slice(0, 45) + (firstUserMsg.content.length > 45 ? '...' : '')
        : 'New Chat'
    }

    try {
      const res = await fetch(`${API}/history`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          session_id: sessionId || undefined,
          title,
          messages: msgs.map(m => ({
            role: m.role,
            content: m.content,
            sources: m.sources || []
          }))
        })
      })
      if (res.ok) {
        const data = await res.json()
        loadHistory()
        return data.session.id
      }
    } catch (e) {
      console.error('Failed to save session:', e)
    }
    return sessionId
  }, [token, loadHistory])

  // ---- Auto-generate smart title ----
  const generateSmartTitle = async (question, answer, sessionId, currentMsgs) => {
    if (!token) return
    try {
      const res = await fetch(`${API}/history/auto-title`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ question, answer })
      })
      if (res.ok) {
        const data = await res.json()
        if (data.title) {
          saveSession(currentMsgs, sessionId, data.title)
        }
      }
    } catch {}
  }

  // ---- Send message with SSE streaming ----
  const sendMessage = async (overrideText) => {
    const question = (overrideText || input).trim()
    if (!question || isLoading) return

    const userMessage = { role: 'user', content: question }
    const updatedMessages = [...messages, userMessage]
    setMessages(updatedMessages)
    setInput('')
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
    }
    setIsLoading(true)

    const chatHistory = messages.map(m => ({
      role: m.role,
      content: m.content
    }))

    // Add placeholder assistant message
    const placeholderAssistant = {
      role: 'assistant',
      content: '',
      statusText: 'Connecting to medical knowledge base...',
      sources: [],
      isStreaming: true
    }
    setMessages([...updatedMessages, placeholderAssistant])

    abortControllerRef.current = new AbortController()

    try {
      const response = await fetch(`${API}/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({ question, chat_history: chatHistory }),
        signal: abortControllerRef.current.signal
      })

      if (!response.ok) {
        // Fallback to non-streaming if stream endpoint fails
        throw new Error(`Server returned status ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let streamBuffer = ''
      let finalSources = []
      let tokenQueue = []
      let displayedText = ''
      let streamDoneReading = false

      // Smooth typewriter delivery
      await new Promise((resolve, reject) => {
        const intervalId = setInterval(() => {
          if (tokenQueue.length > 0) {
            // Take 1 item or up to 3 if queue has many items
            const take = tokenQueue.length > 25 ? 3 : 1
            const chunk = tokenQueue.splice(0, take).join('')
            displayedText += chunk

            setMessages(prev => {
              const copy = [...prev]
              const last = copy[copy.length - 1]
              if (last && last.role === 'assistant') {
                copy[copy.length - 1] = {
                  ...last,
                  content: displayedText,
                  statusText: '',
                  isStreaming: true
                }
              }
              return copy
            })
          } else if (streamDoneReading) {
            clearInterval(intervalId)
            resolve()
          }
        }, 22)

        // Read network stream
        ;(async () => {
          try {
            while (true) {
              const { value, done } = await reader.read()
              if (done) break

              streamBuffer += decoder.decode(value, { stream: true })
              const lines = streamBuffer.split('\n')
              streamBuffer = lines.pop() || ''

              for (const line of lines) {
                const trimmed = line.trim()
                if (!trimmed.startsWith('data: ')) continue

                try {
                  const data = JSON.parse(trimmed.substring(6))
                  if (data.type === 'status') {
                    setMessages(prev => {
                      const copy = [...prev]
                      const last = copy[copy.length - 1]
                      if (last && last.role === 'assistant' && !displayedText) {
                        copy[copy.length - 1] = {
                          ...last,
                          statusText: data.content
                        }
                      }
                      return copy
                    })
                  } else if (data.type === 'token') {
                    if (data.content) {
                      // Split incoming chunk into tokens/words with whitespace preserved
                      const tokens = data.content.match(/\S+|\s+/g) || [data.content]
                      tokenQueue.push(...tokens)
                    }
                  } else if (data.type === 'sources') {
                    finalSources = data.content || []
                  } else if (data.type === 'error') {
                    throw new Error(data.content)
                  }
                } catch (parseErr) {
                  console.warn('SSE parse error:', parseErr)
                }
              }
            }
          } catch (readErr) {
            clearInterval(intervalId)
            reject(readErr)
            return
          }
          streamDoneReading = true
        })()
      })

      const finishedAssistant = {
        role: 'assistant',
        content: displayedText || 'No response generated.',
        sources: finalSources,
        isStreaming: false
      }

      const finalAllMessages = [...updatedMessages, finishedAssistant]
      setMessages(finalAllMessages)

      // Save to chat history
      const isFirstExchange = !activeSessionId && updatedMessages.length === 1
      const savedId = await saveSession(finalAllMessages, activeSessionId)
      if (savedId) {
        setActiveSessionId(savedId)
        if (isFirstExchange && displayedText) {
          generateSmartTitle(question, displayedText, savedId, finalAllMessages)
        }
      }

    } catch (err) {
      if (err.name === 'AbortError') return

      console.error('Streaming error, attempting standard fallback:', err)
      // Fallback: try synchronous chat
      try {
        const fallbackRes = await fetch(`${API}/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          },
          body: JSON.stringify({ question, chat_history: chatHistory })
        })

        if (!fallbackRes.ok) throw new Error(`Error: ${fallbackRes.statusText}`)

        const fbData = await fallbackRes.json()
        const assistantMsg = {
          role: 'assistant',
          content: fbData.answer,
          sources: fbData.sources || [],
          isStreaming: false
        }
        const finalAll = [...updatedMessages, assistantMsg]
        setMessages(finalAll)
        const savedId = await saveSession(finalAll, activeSessionId)
        if (savedId) setActiveSessionId(savedId)

      } catch (fallbackErr) {
        setMessages(prev => {
          const copy = [...prev]
          copy[copy.length - 1] = {
            role: 'assistant',
            content: `⚠️ Failed to get a response: ${err.message}. Please check your connection or Groq API key and try again.`,
            sources: [],
            isError: true,
            originalQuestion: question,
            isStreaming: false
          }
          return copy
        })
      }
    } finally {
      setIsLoading(false)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }

  // ---- Copy to clipboard ----
  const handleCopy = (text, idx) => {
    navigator.clipboard.writeText(text)
    setCopiedIdx(idx)
    setTimeout(() => setCopiedIdx(null), 2000)
  }

  // ---- History actions ----
  const loadSession = async (sessionId) => {
    try {
      const res = await fetch(`${API}/history/${sessionId}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (res.ok) {
        const data = await res.json()
        setMessages(data.session.messages || [])
        setActiveSessionId(sessionId)
        setSidebarOpen(false)
      }
    } catch (e) {
      console.error('Failed to load session:', e)
    }
  }

  const deleteSessionHandler = async (e, sessionId) => {
    e.stopPropagation()
    try {
      await fetch(`${API}/history/${sessionId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      })
      if (activeSessionId === sessionId) {
        setMessages([])
        setActiveSessionId(null)
      }
      loadHistory()
    } catch (e) {
      console.error('Failed to delete session:', e)
    }
  }

  const handleNewChat = () => {
    setMessages([])
    setActiveSessionId(null)
    setInput('')
    setSidebarOpen(false)
    if (inputRef.current) {
      inputRef.current.style.height = 'auto'
      inputRef.current.focus()
    }
  }

  const handleExampleClick = (example) => {
    setSidebarOpen(false)
    setInput(example)
    sendMessage(example)
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const handleTextareaInput = (e) => {
    setInput(e.target.value)
    // Auto-resize
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`
  }

  // ---- Change Password handler ----
  const handleChangePassword = async (e) => {
    e.preventDefault()
    if (!oldPassword || !newPassword) return
    setIsChangingPw(true)
    setPasswordMsg({ type: '', text: '' })

    try {
      const res = await fetch(`${API}/auth/change-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword
        })
      })
      const data = await res.json()
      if (res.ok) {
        setPasswordMsg({ type: 'success', text: 'Password updated successfully!' })
        setOldPassword('')
        setNewPassword('')
        setTimeout(() => {
          setShowPasswordModal(false)
          setPasswordMsg({ type: '', text: '' })
        }, 1500)
      } else {
        setPasswordMsg({ type: 'error', text: data.error || 'Failed to change password' })
      }
    } catch {
      setPasswordMsg({ type: 'error', text: 'Network error. Please try again.' })
    } finally {
      setIsChangingPw(false)
    }
  }

  // ---- Share consultation handler ----
  const handleShareChat = async () => {
    if (messages.length === 0) return
    setShareModal({ open: true, url: '', copied: false, loading: true, error: '' })

    try {
      let currentId = activeSessionId
      if (!currentId) {
        currentId = await saveSession(messages, null)
        if (currentId) setActiveSessionId(currentId)
      }

      if (!currentId) throw new Error('Could not save conversation to share.')

      const res = await fetch(`${API}/history/${currentId}/share`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`
        }
      })
      const data = await res.json()
      if (res.ok && data.share_token) {
        const shareUrl = `${window.location.origin}/?share=${data.share_token}`
        setShareModal({ open: true, url: shareUrl, copied: false, loading: false, error: '' })
        navigator.clipboard.writeText(shareUrl).then(() => {
          setShareModal(prev => ({ ...prev, copied: true }))
          setTimeout(() => setShareModal(prev => ({ ...prev, copied: false })), 2500)
        }).catch(() => {})
      } else {
        throw new Error(data.error || 'Failed to generate share link')
      }
    } catch (err) {
      setShareModal({ open: true, url: '', error: err.message, loading: false, copied: false })
    }
  }

  // ---- Shared consultation view ----
  if (page === 'shared') {
    return (
      <div className="shared-layout">
        <header className="shared-header">
          <div className="shared-brand">
            <div className="brand-icon">🏥</div>
            <div>
              <h2>MediCare AI</h2>
              <p>Shared Clinical Consultation (Read-Only)</p>
            </div>
          </div>
          <div className="shared-header-actions">
            <button className="theme-toggle" onClick={toggleTheme} title="Toggle theme">
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
            <button
              className="btn-save"
              onClick={() => {
                window.history.pushState({}, '', window.location.pathname)
                setPage(token ? 'chat' : 'login')
              }}
            >
              Start New Consultation →
            </button>
          </div>
        </header>

        <main className="shared-main">
          {sharedSession?.error ? (
            <div className="shared-error-card">
              <h3>⚠️ Unable to view conversation</h3>
              <p>{sharedSession.error}</p>
              <button
                className="btn-save"
                onClick={() => {
                  window.history.pushState({}, '', window.location.pathname)
                  setPage(token ? 'chat' : 'login')
                }}
              >
                Go to Home
              </button>
            </div>
          ) : !sharedSession ? (
            <div className="shimmer-loader" style={{ maxWidth: 700, margin: '60px auto' }}>
              <div className="shimmer-line"></div>
              <div className="shimmer-line short"></div>
              <div className="shimmer-line medium"></div>
            </div>
          ) : (
            <div className="shared-conversation-container">
              <div className="shared-meta-banner">
                <div className="shared-title">{sharedSession.title}</div>
                <div className="shared-meta-info">
                  Shared by <strong>{sharedSession.user_name || 'Patient'}</strong> · {sharedSession.created_at ? new Date(sharedSession.created_at).toLocaleDateString() : 'Recent'}
                </div>
              </div>

              <div className="messages-area shared-messages">
                {sharedSession.messages?.map((msg, i) => (
                  <div key={i} className={`message-row ${msg.role}`}>
                    {msg.role === 'user' ? (
                      <div className="user-message-wrapper">
                        <div className="user-bubble">
                          {msg.content}
                        </div>
                      </div>
                    ) : (
                      <div className="assistant-message-wrapper">
                        <div className="msg-avatar assistant">⚕</div>
                        <div className="assistant-content">
                          <div className="markdown-content">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {msg.content}
                            </ReactMarkdown>
                          </div>
                          {msg.sources && msg.sources.length > 0 && (
                            <div className="sources-section">
                              <div className="sources-label">Verified Clinical Sources</div>
                              <div className="sources-tags">
                                {msg.sources.map((src, j) => (
                                  <div key={j} className="source-tag">
                                    <span className="source-page">Page {src.page}</span>
                                    <span className="source-name">{src.source}</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </main>
      </div>
    )
  }

  // ---- Auth views ----
  if (page === 'login') {
    return <Login onLogin={handleAuth} onSwitchToSignup={() => setPage('signup')} />
  }
  if (page === 'signup') {
    return <Signup onSignup={handleAuth} onSwitchToLogin={() => setPage('login')} />
  }

  // ---- Main Chat View ----
  return (
    <div className="app-layout">
      {/* Mobile sidebar toggle button */}
      <button
        className="sidebar-toggle"
        onClick={() => setSidebarOpen(!sidebarOpen)}
        id="sidebar-toggle"
        aria-label="Toggle menu"
      >
        {sidebarOpen ? '✕' : '☰'}
      </button>
      <div
        className={`sidebar-overlay ${sidebarOpen ? 'visible' : ''}`}
        onClick={() => setSidebarOpen(false)}
      />

      {/* Sidebar */}
      <aside
        className={`sidebar ${sidebarOpen ? 'open' : 'closed'} ${isResizing ? 'resizing' : ''}`}
        style={{
          width: sidebarOpen ? `${sidebarWidth}px` : '0px',
          minWidth: sidebarOpen ? `${sidebarWidth}px` : '0px',
        }}
      >
        <div className="sidebar-header">
          <div className="brand">
            <div className="brand-icon">🏥</div>
            <div className="brand-text">
              <h1>MediCare AI</h1>
              <p>Clinical Reference AI</p>
            </div>
          </div>
          <button className="new-chat-btn" onClick={handleNewChat} id="new-chat-btn">
            <span>+</span> New Chat
          </button>
        </div>

        <div className="sidebar-content">
          {/* History */}
          <div className="sidebar-section">
            <div className="sidebar-label">Recent Conversations</div>
            <div className="history-list">
              {sessions.length === 0 ? (
                <div className="empty-history">No conversations yet</div>
              ) : (
                sessions.map(s => (
                  <div
                    key={s.id}
                    className={`history-item ${activeSessionId === s.id ? 'active' : ''}`}
                    onClick={() => loadSession(s.id)}
                  >
                    <span className="history-item-icon">💬</span>
                    <span className="history-item-title">{s.title}</span>
                    <button
                      className="history-delete-btn"
                      onClick={(e) => deleteSessionHandler(e, s.id)}
                      title="Delete conversation"
                      aria-label="Delete conversation"
                    >
                      ✕
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>

          {/* Quick clinical queries */}
          <div className="sidebar-section">
            <div className="sidebar-label">Try Asking</div>
            <div className="example-list">
              {EXAMPLES.map((ex, i) => (
                <div
                  key={i}
                  className="example-item"
                  onClick={() => handleExampleClick(ex)}
                  id={`example-${i}`}
                >
                  <span className="example-bullet">›</span> {ex}
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* User profile & actions */}
        <div className="sidebar-footer">
          <div className="user-section">
            <div className="user-avatar">
              {user?.name?.charAt(0).toUpperCase()}
            </div>
            <div className="user-info">
              <div className="user-name">{user?.name}</div>
              <div className="user-email">{user?.email}</div>
            </div>
          </div>
          <div className="footer-actions">
            <button
              className="footer-btn"
              onClick={() => setShowPasswordModal(true)}
              title="Change Password"
            >
              🔑 Password
            </button>
            <button
              className="footer-btn logout"
              onClick={handleLogout}
              title="Sign out"
            >
              Logout
            </button>
          </div>
        </div>

        {sidebarOpen && (
          <div
            className="sidebar-resizer"
            onMouseDown={startResizing}
            title="Drag to resize sidebar"
          />
        )}
      </aside>

      {/* Main Chat Interface */}
      <main className="main-content">
        <header className="chat-header">
          <div className="chat-header-left">
            <button
              className="sidebar-toggle-btn"
              onClick={() => setSidebarOpen(prev => !prev)}
              title={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
              id="sidebar-desktop-toggle"
              aria-label="Toggle sidebar"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect>
                <line x1="9" y1="3" x2="9" y2="21"></line>
              </svg>
            </button>
            <div className="chat-header-brand-info">
              <h2>MediCare AI</h2>
              <div className="status-badge">
                <span className="status-dot"></span>
                Clinical RAG Active
              </div>
            </div>
          </div>
          <div className="chat-header-right">
            {messages.length > 0 && (
              <button
                className="share-btn"
                onClick={handleShareChat}
                title="Share consultation link"
                id="share-chat-btn"
              >
                <span>🔗</span> Share
              </button>
            )}
            <button
              className="theme-toggle"
              onClick={toggleTheme}
              title={`Switch to ${theme === 'dark' ? 'Light' : 'Dark'} Mode`}
              id="theme-toggle"
            >
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
          </div>
        </header>

        {/* Messages */}
        <div className="messages-area" id="messages-area">
          {messages.length === 0 && !isLoading ? (
            <div className="welcome-container">
              <div className="welcome-card">
                <div className="welcome-icon">🩺</div>
                <h2>Evidence-Based Medical Assistant</h2>
                <p>
                  Ask queries on diseases, diagnoses, etiology, symptoms, or precautions. Responses are grounded in clinical reference literature with hybrid BM25 and vector retrieval.
                </p>
                <div className="welcome-chips">
                  {EXAMPLES.slice(0, 4).map((ex, i) => (
                    <button
                      key={i}
                      className="welcome-chip"
                      onClick={() => handleExampleClick(ex)}
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            <>
              {messages.map((msg, i) => (
                <div key={i} className={`message-row ${msg.role}`}>
                  {msg.role === 'user' ? (
                    <div className="user-message-wrapper">
                      <div className="user-bubble">
                        {msg.content}
                      </div>
                    </div>
                  ) : (
                    <div className="assistant-message-wrapper">
                      <div className="msg-avatar assistant" title="MediCare AI">⚕</div>
                      <div className="assistant-content">
                        <div className="markdown-content">
                          {msg.content ? (
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {msg.content}
                            </ReactMarkdown>
                          ) : (
                            <div className="shimmer-loader">
                              {msg.statusText && (
                                <div className="streaming-status-badge">
                                  <span className="status-pulse-dot"></span>
                                  {msg.statusText}
                                </div>
                              )}
                              <div className="shimmer-line short"></div>
                              <div className="shimmer-line"></div>
                              <div className="shimmer-line medium"></div>
                            </div>
                          )}
                          {msg.isStreaming && <span className="stream-cursor"></span>}
                        </div>

                        {/* Sources section */}
                        {msg.sources && msg.sources.length > 0 && (
                          <div className="sources-section">
                            <div className="sources-label">
                              <span>📚 Verified Clinical Sources</span>
                            </div>
                            <div className="sources-tags">
                              {msg.sources.map((src, j) => (
                                <div key={j} className="source-tag">
                                  <span className="source-page">Page {src.page}</span>
                                  <span className="source-name">{src.source}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}

                        {/* Action bar for assistant messages */}
                        {!msg.isStreaming && (
                          <div className="msg-actions">
                            {msg.content && (
                              <button
                                className="msg-action-btn"
                                onClick={() => handleCopy(msg.content, i)}
                                title="Copy response to clipboard"
                              >
                                {copiedIdx === i ? '✓ Copied!' : '📋 Copy'}
                              </button>
                            )}
                            {msg.isError && msg.originalQuestion && (
                              <button
                                className="msg-action-btn retry"
                                onClick={() => sendMessage(msg.originalQuestion)}
                                title="Retry question"
                              >
                                🔄 Retry
                              </button>
                            )}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {/* Shimmer loading when waiting for first token */}
              {isLoading && messages[messages.length - 1]?.role === 'user' && (
                <div className="message-row assistant">
                  <div className="assistant-message-wrapper">
                    <div className="msg-avatar assistant">⚕</div>
                    <div className="assistant-content">
                      <div className="shimmer-loader">
                        <div className="streaming-status-badge">
                          <span className="status-pulse-dot"></span>
                          Searching medical knowledge base...
                        </div>
                        <div className="shimmer-line short"></div>
                        <div className="shimmer-line"></div>
                        <div className="shimmer-line medium"></div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Input area */}
        <div className="input-area">
          <div className="input-wrapper">
            <textarea
              ref={inputRef}
              className="input-field"
              placeholder="Ask a medical question (e.g. causes of diabetes, symptoms of asthma)..."
              value={input}
              onChange={handleTextareaInput}
              onKeyDown={handleKeyDown}
              disabled={isLoading}
              rows={1}
              id="chat-input"
            />
            <button
              className="send-btn"
              onClick={() => sendMessage()}
              disabled={!input.trim() || isLoading}
              id="send-btn"
              title="Send question (Enter)"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13"></line>
                <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
              </svg>
            </button>
          </div>
          <div className="disclaimer">
            <span>🛡️</span>
            <span><strong>Clinical Disclaimer:</strong> This assistant provides informational content based on medical reference literature and is not intended for personal medical diagnosis or emergency care.</span>
          </div>
        </div>
      </main>

      {/* Change Password Modal */}
      {showPasswordModal && (
        <div className="modal-overlay" onClick={() => setShowPasswordModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Change Password</h3>
              <button
                className="modal-close-btn"
                onClick={() => setShowPasswordModal(false)}
              >
                ✕
              </button>
            </div>
            <form onSubmit={handleChangePassword} className="modal-form">
              {passwordMsg.text && (
                <div className={`modal-alert ${passwordMsg.type}`}>
                  {passwordMsg.text}
                </div>
              )}
              <div className="form-group">
                <label>Current Password</label>
                <input
                  type="password"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  placeholder="Enter current password"
                  required
                />
              </div>
              <div className="form-group">
                <label>New Password (min 6 characters)</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="Enter new password"
                  required
                  minLength={6}
                />
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-cancel"
                  onClick={() => setShowPasswordModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-save"
                  disabled={isChangingPw}
                >
                  {isChangingPw ? 'Updating...' : 'Update Password'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Share Conversation Modal */}
      {shareModal.open && (
        <div className="modal-overlay" onClick={() => setShareModal(prev => ({ ...prev, open: false }))}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Share Conversation</h3>
              <button
                className="modal-close-btn"
                onClick={() => setShareModal(prev => ({ ...prev, open: false }))}
              >
                ✕
              </button>
            </div>
            <div className="modal-form">
              {shareModal.loading ? (
                <div style={{ textAlign: 'center', padding: '24px 10px', color: 'var(--text-secondary)' }}>
                  Generating secure share link...
                </div>
              ) : shareModal.error ? (
                <div className="modal-alert error">
                  {shareModal.error}
                </div>
              ) : (
                <>
                  <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '14px', lineHeight: 1.5 }}>
                    Anyone with this link will be able to view this clinical consultation transcript in read-only mode.
                  </p>
                  <div className="share-link-box">
                    <input
                      type="text"
                      readOnly
                      value={shareModal.url}
                      className="share-input"
                      onClick={(e) => e.target.select()}
                    />
                    <button
                      type="button"
                      className="btn-save"
                      onClick={() => {
                        navigator.clipboard.writeText(shareModal.url)
                        setShareModal(prev => ({ ...prev, copied: true }))
                        setTimeout(() => setShareModal(prev => ({ ...prev, copied: false })), 2500)
                      }}
                    >
                      {shareModal.copied ? '✓ Copied' : 'Copy'}
                    </button>
                  </div>
                  {shareModal.copied && (
                    <div style={{ fontSize: '12px', color: '#10b981', marginTop: '10px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      ✓ Link copied to clipboard!
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
