import React, { useEffect, useMemo, useState } from 'react';
import { History, Loader2, MessageSquare, Plus, Send, TrendingUp } from 'lucide-react';
import './App.css';

const STORAGE_KEY = 'tradebuddy_chat_threads';
const ACTIVE_THREAD_KEY = 'tradebuddy_active_thread';

const initialMessage = {
  sender: 'ai',
  text: 'Hello! I am TradeBuddy. Ask me about any stock (e.g., "Should I buy Apple?") or ask a general market question!'
};

function createThread(title = 'New chat', messages = [initialMessage]) {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    title,
    messages,
    updatedAt: Date.now(),
  };
}

function threadTitleFromMessage(message) {
  const trimmed = message.trim();
  if (!trimmed) return 'New chat';
  return trimmed.length > 28 ? `${trimmed.slice(0, 28)}…` : trimmed;
}

function TradeBuddyApp() {
  const [threads, setThreads] = useState(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length) return parsed;
      } catch {
        // Fall through to a fresh chat.
      }
    }
    return [createThread()];
  });
  const [activeThreadId, setActiveThreadId] = useState(() => localStorage.getItem(ACTIVE_THREAD_KEY) || '');
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
  }, [threads]);

  useEffect(() => {
    localStorage.setItem(ACTIVE_THREAD_KEY, activeThreadId);
  }, [activeThreadId]);

  useEffect(() => {
    if (!activeThreadId && threads[0]) {
      setActiveThreadId(threads[0].id);
    }
  }, [activeThreadId, threads]);

  const activeThread = useMemo(() => {
    return threads.find((thread) => thread.id === activeThreadId) || threads[0];
  }, [threads, activeThreadId]);

  const updateActiveThread = (updater) => {
    setThreads((prev) => prev.map((thread) => {
      if (thread.id !== activeThread?.id) return thread;
      return updater(thread);
    }));
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = input;
    setInput('');
    setLoading(true);

    updateActiveThread((thread) => ({
      ...thread,
      title: thread.messages.length <= 1 ? threadTitleFromMessage(userMessage) : thread.title,
      messages: [...thread.messages, { sender: 'user', text: userMessage }],
      updatedAt: Date.now(),
    }));

    try {
      const response = await fetch('http://127.0.0.1:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage }),
      });

      if (!response.ok) {
        throw new Error(`Server error: ${response.status}`);
      }

      const data = await response.json();

      if (!data || !data.response) {
        throw new Error('Invalid response received from server.');
      }

      updateActiveThread((thread) => ({
        ...thread,
        messages: [
          ...thread.messages,
          {
            sender: 'ai',
            text: data.response,
            ticker: data.ticker_detected !== 'NONE' ? data.ticker_detected : null,
          },
        ],
        updatedAt: Date.now(),
      }));
    } catch (error) {
      updateActiveThread((thread) => ({
        ...thread,
        messages: [
          ...thread.messages,
          {
            sender: 'ai',
            text: error.message || 'Error connecting to local TradeBuddy backend server.',
          },
        ],
        updatedAt: Date.now(),
      }));
    } finally {
      setLoading(false);
    }
  };

  const handleNewChat = () => {
    const freshThread = createThread();
    setThreads((prev) => [freshThread, ...prev]);
    setActiveThreadId(freshThread.id);
    setInput('');
    setLoading(false);
  };

  const openThread = (threadId) => {
    setActiveThreadId(threadId);
    setInput('');
    setLoading(false);
  };

  return (
    <div className="app-container">
      <aside className="sidebar">
        <div className="sidebar-top">
          <div className="logo-section">
            <TrendingUp size={28} className="logo-icon" />
            <h2>TradeBuddy AI</h2>
          </div>
          <button className="new-chat-btn" onClick={handleNewChat}>
            <Plus size={16} />
            <span>New chat</span>
          </button>
        </div>

        <div className="history-section">
          <div className="section-title">
            <History size={16} />
            <span>Previous chats</span>
          </div>
          <div className="chat-history-list">
            {threads.map((thread) => (
              <button
                key={thread.id}
                className={`chat-history-item ${thread.id === activeThread?.id ? 'active' : ''}`}
                onClick={() => openThread(thread.id)}
              >
                <strong>{thread.title}</strong>
                <span>{thread.messages.length} messages</span>
              </button>
            ))}
          </div>
        </div>

        <div className="info-box">
          <h3>Local Agent Status</h3>
          <p>🧠 Brain: <strong>Gemma 3 (4B)</strong></p>
          <p>🔗 Database: <strong>MySQL Connected</strong></p>
        </div>
      </aside>

      <main className="chat-stage">
        <header className="chat-header">
          <MessageSquare size={20} />
          <div>
            <h3>{activeThread?.title || 'TradeBuddy Chat'}</h3>
            <p>AI Assistance Workspace</p>
          </div>
        </header>

        <div className="messages-window">
          {activeThread?.messages.map((msg, index) => (
            <div key={index} className={`message-row ${msg.sender}`}>
              <div className="message-bubble">
                {msg.ticker && <span className="ticker-badge">${msg.ticker}</span>}
                <p>{msg.text}</p>
              </div>
            </div>
          ))}
          {loading && (
            <div className="message-row ai">
              <div className="message-bubble loading-bubble">
                <Loader2 className="spinner" size={18} />
                <span>Gemma 3 is analyzing data...</span>
              </div>
            </div>
          )}
        </div>

        <form className="input-form" onSubmit={handleSendMessage}>
          <input
            type="text"
            placeholder="Type your investment analysis query here..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
          />
          <button type="submit" disabled={loading || !input.trim()}>
            <Send size={18} />
          </button>
        </form>
      </main>
    </div>
  );
}

export default TradeBuddyApp;
