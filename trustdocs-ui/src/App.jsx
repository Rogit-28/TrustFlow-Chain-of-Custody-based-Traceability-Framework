import React, { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { ToastProvider, useToast } from './components/ui/toast';
import { Shield, LayoutDashboard, FolderOpen, LogOut, User, Users, Share2, Trash2, Crosshair, PanelLeftClose, PanelLeftOpen } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

import AuthView from './views/AuthView';
import Workspace from './views/Workspace';
import SharedView from './views/SharedView';
import RecycleBinView from './views/RecycleBinView';
import AdminDashboard from './views/AdminDashboard';
import LeakDetectionView from './views/LeakDetectionView';
import BoardroomView from './views/BoardroomView';
import BoardroomDetail from './views/BoardroomDetail';

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
  const [isCollapsed, setIsCollapsed] = useState(false);

  const handleLogout = async () => { await logout(); navigate('/auth'); };

  const navItems = [
    { name: 'Workspace', path: '/', icon: FolderOpen },
    { name: 'Shared', path: '/shared', icon: Share2 },
    { name: 'Recycle Bin', path: '/recycle', icon: Trash2 },
    { name: 'Inner Circle', path: '/boardroom', icon: Users },
    { name: 'Mission Control', path: '/forensics', icon: Crosshair },
    { name: 'Leak Detection', path: '/leak-detection', icon: Shield },
  ];

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ── Sidebar ── */}
      <motion.aside
        initial={false}
        animate={{ width: isCollapsed ? 80 : 240 }}
        transition={{ type: "spring", damping: 30, stiffness: 300 }}
        className="border-r border-white/[0.06] bg-[#050505] flex flex-col z-20 shrink-0"
      >
        {/* Brand */}
        <div className="p-5 flex items-center justify-between min-h-[72px] relative overflow-hidden">
          <motion.div
            initial={false}
            animate={{ opacity: isCollapsed ? 0 : 1, x: isCollapsed ? -20 : 0 }}
            transition={{ duration: 0.2 }}
            className={`flex items-center gap-3 ${isCollapsed ? 'pointer-events-none absolute' : ''}`}
          >
            <div className="p-2 rounded-lg border border-red-500/30 bg-red-500/5 shadow-[0_0_12px_rgba(255,7,58,0.2)] shrink-0">
              <Shield className="h-5 w-5 text-red-500" />
            </div>
            <span className="font-display font-bold text-lg tracking-tight text-white whitespace-nowrap">TrustDocs</span>
          </motion.div>

          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className={`text-gray-500 hover:text-white transition-colors absolute right-4 flex items-center justify-center h-8 w-8 rounded hover:bg-white/[0.04] ${isCollapsed ? 'left-1/2 -translate-x-1/2 right-auto' : ''}`}
          >
            {isCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        </div>

        {/* Nav */}
        <nav className="flex-1 px-3 space-y-1 mt-3 overflow-y-auto overflow-x-hidden">
          {navItems.map((item) => {
            const isActive = location.pathname === item.path;
            const Icon = item.icon;
            return (
              <button
                key={item.path}
                onClick={() => navigate(item.path)}
                className={`w-full flex items-center px-3 py-3 rounded-lg text-sm font-medium transition-all duration-300 cursor-pointer overflow-hidden group relative ${isActive
                  ? 'text-white bg-gradient-to-r from-red-500/[0.08] to-transparent border border-white/5 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.05)]'
                  : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.02] border border-transparent hover:border-white/[0.04]'
                  }`}
                title={isCollapsed ? item.name : undefined}
              >
                {isActive && <div className="absolute left-0 top-0 bottom-0 w-1 bg-red-500 rounded-r-full" />}
                <div className={`flex items-center justify-center shrink-0 w-8 ${isCollapsed ? 'mx-auto' : 'mr-3'}`}>
                  <Icon className={`h-4 w-4 transition-colors ${isActive ? 'text-red-500' : 'group-hover:text-gray-300'}`} />
                </div>
                <motion.span
                  initial={false}
                  animate={{ opacity: isCollapsed ? 0 : 1, width: isCollapsed ? 0 : 'auto', marginLeft: isCollapsed ? 0 : 4 }}
                  className="whitespace-nowrap overflow-hidden"
                >
                  {item.name}
                </motion.span>
              </button>
            )
          })}
        </nav>

        {/* User section */}
        <div className={`p-3 mt-auto border-t border-white/[0.06] overflow-hidden`}>
          <div className={`flex items-center px-2 py-2 mb-2 relative ${isCollapsed ? 'justify-center' : ''}`}>
            <div className="h-8 w-8 rounded-full bg-white/10 flex items-center justify-center shrink-0 z-10" title={isCollapsed ? user?.username : undefined}>
              <User className="h-4 w-4 text-gray-400" />
            </div>
            <motion.div
              initial={false}
              animate={{ opacity: isCollapsed ? 0 : 1, width: isCollapsed ? 0 : 'auto', marginLeft: isCollapsed ? 0 : 12 }}
              className="flex flex-col min-w-0 pr-2 overflow-hidden whitespace-nowrap"
            >
              <span className="text-xs font-semibold text-white truncate">{user?.username}</span>
              <span className="text-[10px] text-gray-600 truncate font-mono">{user?.id?.substring(0, 8)}</span>
            </motion.div>
          </div>
          <button
            onClick={handleLogout}
            className={`w-full flex items-center px-3 py-2 text-xs text-gray-500 hover:text-red-400 hover:bg-red-500/5 rounded-lg transition-colors cursor-pointer group relative`}
            title={isCollapsed ? "Sign Out" : undefined}
          >
            <div className={`flex items-center justify-center shrink-0 w-8 ${isCollapsed ? 'mx-auto' : 'mr-1'}`}>
              <LogOut className={`h-3.5 w-3.5 ${isCollapsed ? 'group-hover:text-red-400' : ''}`} />
            </div>
            <motion.span
              initial={false}
              animate={{ opacity: isCollapsed ? 0 : 1, width: isCollapsed ? 0 : 'auto', marginLeft: isCollapsed ? 0 : 4 }}
              className="whitespace-nowrap overflow-hidden"
            >
              Sign Out
            </motion.span>
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
      <Route path="/boardroom" element={<ProtectedRoute><MainLayout><BoardroomView /></MainLayout></ProtectedRoute>} />
      <Route path="/boardroom/:id" element={<ProtectedRoute><MainLayout><BoardroomDetail /></MainLayout></ProtectedRoute>} />
      <Route path="/forensics" element={<ProtectedRoute><MainLayout><AdminDashboard /></MainLayout></ProtectedRoute>} />
      <Route path="/leak-detection" element={<ProtectedRoute><MainLayout><LeakDetectionView /></MainLayout></ProtectedRoute>} />
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
