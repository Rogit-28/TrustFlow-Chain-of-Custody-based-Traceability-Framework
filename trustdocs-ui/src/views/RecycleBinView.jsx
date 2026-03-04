import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { useToast } from '../components/ui/toast';
import { formatBytes } from '../lib/utils';
import {
    Trash2, RotateCcw, FolderOpen, Shield, Hash, Users, Activity
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import GlobalSearch from '../components/GlobalSearch';

export default function RecycleBinView() {
    const [docs, setDocs] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [restoreModal, setRestoreModal] = useState(null);
    const toast = useToast();
    const location = useLocation();
    const docRefs = useRef({});

    const fetchRecycled = async () => {
        setIsLoading(true);
        try {
            const res = await axios.get('/documents/recycled');
            setDocs(res.data);
        } catch (err) {
            toast({ title: 'Error loading recycled docs', description: err.message, type: 'error' });
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => { fetchRecycled(); }, []);

    // Scroll to doc from GlobalSearch
    useEffect(() => {
        if (location.state?.scrollTo) {
            setTimeout(() => {
                const el = docRefs.current[location.state.scrollTo];
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 300);
        }
    }, [location.state]);

    const handleRestore = async (doc, restoreAccess) => {
        try {
            await axios.post(`/documents/${doc.id}/restore`, { restore_access: restoreAccess });
            toast({ title: 'Restored', description: restoreAccess ? 'Shares reactivated.' : 'Restored with no shares.', type: 'success' });
            setRestoreModal(null);
            fetchRecycled();
        } catch { toast({ title: 'Restore failed', type: 'error' }); }
    };

    const handlePurge = async (doc) => {
        try {
            await axios.delete(`/documents/${doc.id}/purge`);
            toast({ title: 'Purged', description: 'Document permanently deleted.', type: 'success' });
            fetchRecycled();
        } catch { toast({ title: 'Purge failed', type: 'error' }); }
    };

    return (
        <div className="h-full flex flex-col">
            <div className="mb-6">
                <h1 className="text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
                    <Trash2 className="h-6 w-6 text-gray-500" /> Recycle Bin
                </h1>
                <p className="text-gray-600 text-sm mt-0.5">Soft-deleted documents. Restore or permanently purge.</p>
            </div>

            <GlobalSearch />

            {isLoading ? (
                <div className="flex-1 flex items-center justify-center"><Activity className="h-6 w-6 text-gray-600 animate-spin" /></div>
            ) : docs.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-16 border border-white/[0.04] bg-white/[0.01] rounded-xl border-dashed">
                    <Trash2 className="h-10 w-10 text-gray-700 mb-3" />
                    <p className="text-gray-600 text-sm">Recycle bin is empty.</p>
                </div>
            ) : (
                <motion.div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3"
                    initial="hidden" animate="visible"
                    variants={{ hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.04 } } }}
                >
                    {docs.map((doc) => (
                        <motion.div key={doc.id} ref={el => docRefs.current[doc.id] = el} variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }}>
                            <Card className="group cursor-default transition-all duration-200 relative h-full flex flex-col border-white/[0.04] bg-white/[0.01]">
                                <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-red-500/20 to-transparent" />
                                <CardContent className="p-4 flex-1 flex flex-col opacity-70">
                                    <div className="flex justify-between items-start mb-3">
                                        <div className="p-1.5 bg-white/[0.04] rounded-md">
                                            <Trash2 className="h-5 w-5 text-gray-500" />
                                        </div>
                                        <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border text-red-400/80 border-red-500/20 bg-red-500/5">Recycled</span>
                                    </div>
                                    <h3 className="font-medium text-sm text-gray-200 truncate mb-1">{doc.filename}</h3>
                                    <div className="text-[10px] text-gray-600 font-mono mb-3 truncate flex items-center gap-1">
                                        <Hash className="h-2.5 w-2.5" />{doc.content_hash.substring(0, 12)}
                                    </div>
                                    <div className="mt-auto flex items-center justify-between text-[10px] text-gray-600">
                                        <span>{formatBytes(doc.size_bytes)}</span>
                                        {doc.share_count > 0 && <span className="flex items-center gap-0.5"><Users className="h-2.5 w-2.5" />{doc.share_count}</span>}
                                    </div>
                                </CardContent>
                                <div className="border-t border-white/[0.04] bg-black/40 p-1.5 flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" onClick={() => setRestoreModal(doc)}>
                                        <RotateCcw className="h-3 w-3" /> Restore
                                    </Button>
                                    <Button size="sm" variant="ghost" className="h-7 text-xs text-red-500/60 hover:text-red-400 hover:bg-red-500/10 gap-1"
                                        onClick={() => handlePurge(doc)}>
                                        <Trash2 className="h-3 w-3" /> Purge
                                    </Button>
                                </div>
                            </Card>
                        </motion.div>
                    ))}
                </motion.div>
            )}

            {/* Restore Options Modal */}
            <AnimatePresence>
                {restoreModal && (
                    <>
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-black/70 z-50" onClick={() => setRestoreModal(null)} />
                        <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }} className="fixed inset-0 m-auto w-full max-w-sm h-fit z-50 p-4">
                            <Card>
                                <div className="p-6">
                                    <h3 className="text-lg font-display font-bold mb-1 flex items-center gap-2"><RotateCcw className="h-4 w-4 text-white" /> Restore Document</h3>
                                    <p className="text-gray-500 text-xs mb-5">Choose how to restore <span className="text-white">{restoreModal.filename}</span>.</p>
                                    <div className="space-y-2">
                                        <Button className="w-full gap-2 justify-start" variant="secondary" onClick={() => handleRestore(restoreModal, true)}>
                                            <Shield className="h-4 w-4" /> Restore with existing shares
                                        </Button>
                                        <Button className="w-full gap-2 justify-start" variant="ghost" onClick={() => handleRestore(restoreModal, false)}>
                                            <FolderOpen className="h-4 w-4" /> Restore fresh (no shares)
                                        </Button>
                                    </div>
                                    <div className="flex justify-end mt-4">
                                        <Button variant="ghost" size="sm" onClick={() => setRestoreModal(null)}>Cancel</Button>
                                    </div>
                                </div>
                            </Card>
                        </motion.div>
                    </>
                )}
            </AnimatePresence>
        </div>
    );
}
