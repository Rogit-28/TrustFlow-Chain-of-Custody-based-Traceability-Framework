import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { ToastProvider, useToast } from './components/ui/toast';
import { Shield, LayoutDashboard, FolderOpen, LogOut, User, Share2, Trash2, Crosshair } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

import AuthView from './views/AuthView';
import Workspace from './views/Workspace';
import SharedView from './views/SharedView';
import RecycleBinView from './views/RecycleBinView';
import AdminDashboard from './views/AdminDashboard';

axios.defaults.withCredentials = true;

// ── Auth Context ────────────────────────────────────────

export const AuthContext = React.createContext(null);
export const useAuth = () => React.useContext(AuthContext);

const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => { checkSession(); }, []);

  // Ping backend every 60s to maintain presence
  useEffect(() => {
    if (!user) return;
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') {
        axios.post('/auth/heartbeat').catch(() => { });
      }
    }, 60000);
    return () => clearInterval(interval);
  }, [user]);

  const checkSession = async () => {
    try { const res = await axios.get('/auth/me'); setUser(res.data); }
    catch { setUser(null); }
    finally { setIsLoading(false); }
  };

  const login = async (username, password) => {
    const res = await axios.post('/auth/login', { username, password });
    setUser(res.data.user);
    return res.data;
  };

  const register = async (username, email, password) => {
    const res = await axios.post('/auth/register', { username, email, password });
    return res.data;
  };

  const logout = async () => { await axios.post('/auth/logout'); setUser(null); };

  return (
    <AuthContext.Provider value={{ user, login, register, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
};

// ── Protected Route ─────────────────────────────────────

const ProtectedRoute = ({ children }) => {
  const { user, isLoading } = useAuth();
  if (isLoading) return <div className="flex h-screen items-center justify-center"><div className="h-6 w-6 animate-spin rounded-full border-b-2 border-white"></div></div>;
  if (!user) return <Navigate to="/auth" />;
  return children;
};

// ── Main Layout ─────────────────────────────────────────

const MainLayout = ({ children }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => { await logout(); navigate('/auth'); };

  const navItems = [
    { name: 'Workspace', path: '/', icon: FolderOpen },
    { name: 'Shared', path: '/shared', icon: Share2 },
    { name: 'Recycle Bin', path: '/recycle', icon: Trash2 },
    { name: 'Forensics', path: '/forensics', icon: Crosshair },
  ];

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── Sidebar ── */}
      <motion.aside
        initial={{ x: -260 }} animate={{ x: 0 }}
        transition={{ type: "spring", damping: 30, stiffness: 300 }}
        className="w-60 border-r border-white/[0.06] bg-[#050505] flex flex-col z-20"
      >
        {/* Brand */}
        <div className="p-5 flex items-center gap-3">
          <div className="p-2 rounded-lg border border-red-500/30 bg-red-500/5 shadow-[0_0_12px_rgba(255,7,58,0.2)]">
            <Shield className="h-5 w-5 text-red-500" />
          </div>
          <span className="font-display font-bold text-lg tracking-tight text-white">TrustDocs</span>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 space-y-1 mt-2">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path;
            const Icon = item.icon;
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-300 cursor-pointer ${isActive
                  ? 'text-white bg-gradient-to-r from-red-500/[0.08] to-transparent border border-white/5 border-l-2 border-l-red-500 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.05)]'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.02] border border-transparent hover:border-white/[0.04]'
                  }`}
              >
                <Icon className={`h-4 w-4 transition-colors ${isActive ? 'text-red-500' : ''}`} />
                {item.name}
              </button>
            )
          })}
        </nav>

        {/* User section */}
        <div className="p-3 mt-auto border-t border-white/[0.06]">
          <div className="flex items-center gap-3 px-2 py-2 mb-2">
            <div className="h-7 w-7 rounded-full bg-white/10 flex items-center justify-center">
              <User className="h-3.5 w-3.5 text-gray-400" />
            </div>
            <div className="flex flex-col overflow-hidden">
              <span className="text-xs font-semibold text-white truncate">{user?.username}</span>
              <span className="text-[10px] text-gray-600 truncate font-mono">{user?.id?.substring(0, 8)}</span>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full flex items-center justify-center gap-2 px-3 py-2 text-xs text-gray-500 hover:text-red-400 hover:bg-red-500/5 rounded-lg transition-colors cursor-pointer"
          >
            <LogOut className="h-3.5 w-3.5" />
            Sign Out
          </button>
        </div>
      </motion.aside>

      {/* ── Main ── */}
      <main className="flex-1 overflow-y-auto bg-[#0a0a0a] bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-white/[0.02] to-transparent">
        <div className="h-full p-8 md:p-10 max-w-7xl mx-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={location.pathname}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2 }}
              className="h-full"
            >
              {children}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
};

function AppRoutes() {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;
  return (
    <Routes>
      <Route path="/auth" element={!user ? <AuthView /> : <Navigate to="/" />} />
      <Route path="/" element={<ProtectedRoute><MainLayout><Workspace /></MainLayout></ProtectedRoute>} />
      <Route path="/shared" element={<ProtectedRoute><MainLayout><SharedView /></MainLayout></ProtectedRoute>} />
      <Route path="/recycle" element={<ProtectedRoute><MainLayout><RecycleBinView /></MainLayout></ProtectedRoute>} />
      <Route path="/forensics" element={<ProtectedRoute><MainLayout><AdminDashboard /></MainLayout></ProtectedRoute>} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
