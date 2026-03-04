import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useToast } from '../components/ui/toast';
import { formatBytes } from '../lib/utils';
import {
    FileText, Share2, Download, Hash, Users, Activity, FolderOpen, User
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import GlobalSearch from '../components/GlobalSearch';

export default function SharedView() {
    const [docs, setDocs] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isShareModalOpen, setIsShareModalOpen] = useState(false);
    const [selectedDoc, setSelectedDoc] = useState(null);
    const [shareUsername, setShareUsername] = useState('');
    const toast = useToast();
    const location = useLocation();
    const docRefs = useRef({});

    const fetchSharedDocs = async () => {
        try {
            const res = await axios.get('/documents');
            setDocs(res.data.shared_with_me || []);
        } catch (err) {
            toast({ title: 'Error loading shared docs', description: err.message, type: 'error' });
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchSharedDocs();
    }, []);

    // Scroll to doc from GlobalSearch
    useEffect(() => {
        if (location.state?.scrollTo) {
            setTimeout(() => {
                const el = docRefs.current[location.state.scrollTo];
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 300);
        }
    }, [location.state]);

    const handleDownload = async (doc) => {
        try {
            const res = await axios.get(`/documents/${doc.id}/download`, { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement('a'); link.href = url; link.setAttribute('download', doc.filename);
            document.body.appendChild(link); link.click(); document.body.removeChild(link);
        } catch (err) {
            toast({ title: 'Download failed', type: 'error' });
        }
    };

    const handleShare = async (e) => {
        e.preventDefault();
        if (!selectedDoc || !shareUsername) return;
        try {
            await axios.post(`/documents/${selectedDoc.id}/share`, { recipient_username: shareUsername });
            toast({ title: 'Shared', description: `Watermarked copy sent to ${shareUsername}.`, type: 'success' });
            setIsShareModalOpen(false); setShareUsername(''); fetchSharedDocs();
        } catch (err) { toast({ title: 'Share failed', description: err.response?.data?.detail || err.message, type: 'error' }); }
    };

    return (
        <div className="h-full flex flex-col">
            <div className="mb-6">
                <h1 className="text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
                    <Share2 className="h-6 w-6 text-gray-500" /> Shared With Me
                </h1>
                <p className="text-gray-600 text-sm mt-0.5">Documents shared to you by other users.</p>
            </div>

            <GlobalSearch />

            {isLoading ? (
                <div className="flex-1 flex items-center justify-center"><Activity className="h-6 w-6 text-gray-600 animate-spin" /></div>
            ) : docs.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-16 border border-white/[0.04] bg-white/[0.01] rounded-xl border-dashed">
                    <FolderOpen className="h-10 w-10 text-gray-700 mb-3" />
                    <p className="text-gray-600 text-sm">No documents shared with you yet.</p>
                </div>
            ) : (
                <motion.div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3"
                    initial="hidden" animate="visible"
                    variants={{ hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.04 } } }}
                >
                    {docs.map((doc) => (
                        <motion.div key={doc.id} ref={el => docRefs.current[doc.id] = el} variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }}>
                            <Card className="group cursor-pointer hover:border-white/10 transition-all duration-200 relative h-full flex flex-col">
                                <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-white/[0.06] to-transparent group-hover:via-emerald-500/30 transition-colors duration-300" />
                                <CardContent className="p-4 flex-1 flex flex-col">
                                    <div className="flex justify-between items-start mb-3">
                                        <div className="p-1.5 bg-white/[0.04] rounded-md">
                                            <FileText className="h-5 w-5 text-gray-500" />
                                        </div>
                                        <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border text-emerald-400/80 border-emerald-500/20 bg-emerald-500/5">Shared</span>
                                    </div>
                                    <h3 className="font-medium text-sm text-gray-200 truncate mb-1">{doc.filename}</h3>
                                    <div className="text-[10px] text-gray-600 font-mono mb-3 truncate flex items-center gap-1">
                                        <Hash className="h-2.5 w-2.5" />{doc.content_hash.substring(0, 12)}
                                    </div>
                                    <div className="mt-auto flex items-center justify-between text-[10px] text-gray-600">
                                        <span>{formatBytes(doc.size_bytes)}</span>
                                    </div>
                                </CardContent>
                                <div className="border-t border-white/[0.04] bg-black/40 p-1.5 flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => handleDownload(doc)}><Download className="h-3.5 w-3.5" /></Button>
                                    <Button size="icon" variant="ghost" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); setSelectedDoc(doc); setIsShareModalOpen(true); }}><Share2 className="h-3.5 w-3.5" /></Button>
                                </div>
                            </Card>
                        </motion.div>
                    ))}
                </motion.div>
            )}

            {/* Share Modal */}
            <AnimatePresence>
                {isShareModalOpen && selectedDoc && (
                    <>
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-black/70 z-50" onClick={() => setIsShareModalOpen(false)} />
                        <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }} className="fixed inset-0 m-auto w-full max-w-md h-fit z-50 p-4">
                            <Card>
                                <div className="p-6">
                                    <h3 className="text-lg font-display font-bold mb-1 flex items-center gap-2"><Share2 className="h-4 w-4 text-white" /> Share</h3>
                                    <p className="text-gray-500 text-xs mb-5">Steganographic watermark embedded for <span className="text-white">{selectedDoc.filename}</span>.</p>
                                    <form onSubmit={handleShare} className="space-y-3">
                                        <Input icon={User} placeholder="Recipient username" required value={shareUsername} onChange={e => setShareUsername(e.target.value)} />
                                        <div className="flex justify-end gap-2 pt-1">
                                            <Button type="button" variant="ghost" onClick={() => setIsShareModalOpen(false)}>Cancel</Button>
                                            <Button type="submit" disabled={!shareUsername}>Share</Button>
                                        </div>
                                    </form>
                                </div>
                            </Card>
                        </motion.div>
                    </>
                )}
            </AnimatePresence>
        </div>
    );
}
