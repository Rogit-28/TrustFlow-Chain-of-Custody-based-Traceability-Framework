import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, FileText, FolderOpen, Share2, Trash2, Activity } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { formatBytes } from '../lib/utils';
import axios from 'axios';

export default function GlobalSearch() {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState([]);
    const [isSearching, setIsSearching] = useState(false);
    const [showDropdown, setShowDropdown] = useState(false);
    const ref = useRef(null);
    const navigate = useNavigate();

    // Close on outside click
    useEffect(() => {
        const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setShowDropdown(false); };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    // Debounced search
    useEffect(() => {
        if (!query.trim()) { setResults([]); setShowDropdown(false); return; }
        const timeout = setTimeout(async () => {
            setIsSearching(true);
            try {
                const res = await axios.get(`/documents/search?q=${encodeURIComponent(query)}`);
                const flat = [
                    ...(res.data.owned || []).map(d => ({ ...d, _source: 'workspace' })),
                    ...(res.data.shared_with_me || []).map(d => ({ ...d, _source: 'shared' })),
                    ...(res.data.recycled || []).map(d => ({ ...d, _source: 'recycle' })),
                ];
                setResults(flat);
                setShowDropdown(flat.length > 0);
            } catch { setResults([]); }
            finally { setIsSearching(false); }
        }, 200);
        return () => clearTimeout(timeout);
    }, [query]);

    const sourceConfig = {
        workspace: { label: 'Workspace', icon: FolderOpen, path: '/', color: 'text-white/50' },
        shared: { label: 'Shared', icon: Share2, path: '/shared', color: 'text-emerald-500/60' },
        recycle: { label: 'Recycle Bin', icon: Trash2, path: '/recycle', color: 'text-red-500/60' },
    };

    const handleSelect = (doc) => {
        const cfg = sourceConfig[doc._source];
        setShowDropdown(false);
        setQuery('');
        navigate(cfg.path, { state: { scrollTo: doc.id } });
    };

    return (
        <div ref={ref} className="relative mb-6">
            <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-600" />
                <input
                    type="text"
                    placeholder="Search all documents..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onFocus={() => results.length > 0 && setShowDropdown(true)}
                    className="w-full pl-10 pr-4 py-2.5 bg-white/[0.03] border border-white/[0.06] rounded-xl text-sm text-white placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-red-500/30 focus:border-red-500/20 transition-all"
                />
                {isSearching && <Activity className="absolute right-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-600 animate-spin" />}
            </div>
            <AnimatePresence>
                {showDropdown && (
                    <motion.div
                        initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                        className="absolute top-full mt-1 w-full bg-[#0a0a0a] border border-white/[0.08] rounded-xl shadow-2xl z-30 max-h-72 overflow-y-auto"
                    >
                        {results.map((doc) => {
                            const cfg = sourceConfig[doc._source];
                            const Icon = cfg.icon;
                            return (
                                <button
                                    key={`${doc._source}-${doc.id}`}
                                    onClick={() => handleSelect(doc)}
                                    className="w-full flex items-center gap-3 px-4 py-3 hover:bg-white/[0.04] transition-colors text-left border-b border-white/[0.04] last:border-b-0 cursor-pointer"
                                >
                                    <FileText className="h-4 w-4 text-gray-500 shrink-0" />
                                    <div className="min-w-0 flex-1">
                                        <div className="text-sm text-gray-200 truncate">{doc.filename}</div>
                                        <div className="text-[10px] text-gray-600 font-mono">{doc.content_hash?.substring(0, 12)}</div>
                                    </div>
                                    <div className={`flex items-center gap-1 text-[10px] shrink-0 ${cfg.color}`}>
                                        <Icon className="h-3 w-3" />
                                        <span>{cfg.label}</span>
                                    </div>
                                </button>
                            );
                        })}
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
