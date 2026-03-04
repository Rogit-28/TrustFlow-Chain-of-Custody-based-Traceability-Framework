import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { Card, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useToast } from '../components/ui/toast';
import { formatBytes } from '../lib/utils';
import {
    FileText, UploadCloud, Share2, Download, Trash2, Shield, FolderOpen,
    MessageSquare, ChevronRight, Hash, Users, Activity, X, User, Star,
    Eye, Image as ImageIcon, FileCode
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';
import { useAuth } from '../App';
import GlobalSearch from '../components/GlobalSearch';

// ── Pin helpers (localStorage) ──────────────────────────
const PIN_KEY = 'trustdocs_pinned';
const getPinned = () => { try { return JSON.parse(localStorage.getItem(PIN_KEY) || '[]'); } catch { return []; } };
const togglePin = (id) => {
    const pinned = getPinned();
    const next = pinned.includes(id) ? pinned.filter(p => p !== id) : [...pinned, id];
    localStorage.setItem(PIN_KEY, JSON.stringify(next));
    return next;
};

// Preview-able MIME types
const PREVIEW_IMAGE = /^image\/(png|jpe?g|gif|webp|svg\+xml|bmp)$/;
const PREVIEW_TEXT = /^text\/(plain|csv|markdown|html|css|javascript|xml)/;
const PREVIEW_PDF = /^application\/pdf$/;
const canPreview = (mime) => PREVIEW_IMAGE.test(mime) || PREVIEW_TEXT.test(mime) || PREVIEW_PDF.test(mime);

export default function Workspace() {
    const [docs, setDocs] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [fileToUpload, setFileToUpload] = useState(null);
    const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
    const [isShareModalOpen, setIsShareModalOpen] = useState(false);
    const [selectedDoc, setSelectedDoc] = useState(null);
    const [shareUsername, setShareUsername] = useState('');
    const [isDrawerOpen, setIsDrawerOpen] = useState(false);
    const [activeDocContext, setActiveDocContext] = useState(null);
    const [pinnedIds, setPinnedIds] = useState(getPinned());
    const [deleteTarget, setDeleteTarget] = useState(null);

    const docRefs = useRef({});
    const toast = useToast();
    const { user } = useAuth();
    const location = useLocation();

    const fetchDocs = async () => {
        setIsLoading(true);
        try {
            const res = await axios.get('/documents');
            setDocs(res.data.owned || []);
        } catch (err) {
            toast({ title: 'Error loading workspace', description: err.message, type: 'error' });
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => { fetchDocs(); }, []);

    // Scroll to doc from GlobalSearch navigation
    useEffect(() => {
        if (location.state?.scrollTo) {
            setTimeout(() => {
                const el = docRefs.current[location.state.scrollTo];
                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 300);
        }
    }, [location.state]);

    const handleUpload = async (e) => {
        e.preventDefault();
        if (!fileToUpload) return;
        const formData = new FormData();
        formData.append('file', fileToUpload);
        try {
            await axios.post('/documents', formData, { headers: { 'Content-Type': 'multipart/form-data' } });
            toast({ title: 'Uploaded', description: 'CoC root created.', type: 'success' });
            setIsUploadModalOpen(false); setFileToUpload(null); fetchDocs();
        } catch (err) { toast({ title: 'Upload failed', description: err.message, type: 'error' }); }
    };

    const handleShare = async (e) => {
        e.preventDefault();
        if (!selectedDoc || !shareUsername) return;
        try {
            await axios.post(`/documents/${selectedDoc.id}/share`, { recipient_username: shareUsername });
            toast({ title: 'Shared', description: `Watermarked copy sent to ${shareUsername}.`, type: 'success' });
            setIsShareModalOpen(false); setShareUsername(''); fetchDocs();
        } catch (err) { toast({ title: 'Share failed', description: err.response?.data?.detail || err.message, type: 'error' }); }
    };

    const handleDownload = async (doc, e) => {
        e.stopPropagation();
        try {
            const res = await axios.get(`/documents/${doc.id}/download`, { responseType: 'blob' });
            const url = window.URL.createObjectURL(new Blob([res.data]));
            const link = document.createElement('a'); link.href = url; link.setAttribute('download', doc.filename);
            document.body.appendChild(link); link.click(); document.body.removeChild(link);
        } catch (err) {
            toast({ title: err.response?.status === 409 ? 'Deleted' : 'Download failed', type: 'error' });
        }
    };

    const handleDelete = async (doc) => {
        try {
            await axios.delete(`/documents/${doc.id}`);
            toast({ title: 'Moved to Bin', description: 'Document recycled.', type: 'success' });
            setDeleteTarget(null);
            fetchDocs();
        } catch { toast({ title: 'Move to Bin failed', type: 'error' }); }
    };

    const handleTogglePin = (doc, e) => {
        e.stopPropagation();
        const next = togglePin(doc.id);
        setPinnedIds(next);
    };

    const openDrawer = async (doc) => {
        try { const res = await axios.get(`/documents/${doc.id}`); setActiveDocContext(res.data); setIsDrawerOpen(true); }
        catch { toast({ title: 'Failed to load context', type: 'error' }); }
    };

    // Split docs
    const pinnedDocs = docs.filter(d => pinnedIds.includes(d.id));
    const unpinnedDocs = docs.filter(d => !pinnedIds.includes(d.id));

    const renderDocCard = (doc) => {
        const isPinned = pinnedIds.includes(doc.id);
        return (
            <motion.div key={doc.id} ref={el => docRefs.current[doc.id] = el} variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }}>
                <Card className="group cursor-pointer border-white/[0.04] bg-[#050505] hover:bg-[#0a0a0a] hover:border-white/[0.12] hover:-translate-y-1 hover:shadow-[0_12px_40px_-10px_rgba(0,0,0,0.8)] transition-all duration-300 relative h-full flex flex-col"
                    onClick={() => openDrawer(doc)}>
                    <div className={`absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent ${isPinned ? 'via-amber-500/40' : 'via-white/[0.06]'} to-transparent group-hover:via-red-500/40 transition-colors duration-500`} />
                    <CardContent className="p-4 flex-1 flex flex-col">
                        <div className="flex justify-between items-start mb-3">
                            <div className="p-1.5 bg-white/[0.04] rounded-md">
                                <FileText className="h-5 w-5 text-gray-500" />
                            </div>
                            <div className="flex items-center gap-1">
                                {isPinned && <Star className="h-3 w-3 text-amber-500 fill-amber-500" />}
                                <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border text-white/60 border-white/10 bg-white/[0.04]">Owner</span>
                            </div>
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
                    <div className="border-t border-white/[0.04] bg-black/40 p-1.5 flex justify-end gap-1 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                        <Button size="icon" variant="ghost" className={`h-7 w-7 transition-colors ${isPinned ? 'text-amber-500 hover:bg-amber-500/10' : ''}`} onClick={(e) => handleTogglePin(doc, e)} title={isPinned ? "Unpin" : "Pin"}>
                            <Star className={`h-3.5 w-3.5 ${isPinned ? 'fill-amber-500' : ''}`} />
                        </Button>
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={(e) => handleDownload(doc, e)}><Download className="h-3.5 w-3.5" /></Button>
                        <Button size="icon" variant="ghost" className="h-7 w-7" onClick={(e) => { e.stopPropagation(); setSelectedDoc(doc); setIsShareModalOpen(true); }}><Share2 className="h-3.5 w-3.5" /></Button>
                        <Button size="icon" variant="ghost" className="h-7 w-7 text-red-500/60 hover:text-red-400 hover:bg-red-500/10" onClick={(e) => { e.stopPropagation(); setDeleteTarget(doc); }}><Trash2 className="h-3.5 w-3.5" /></Button>
                    </div>
                </Card>
            </motion.div>
        );
    };

    return (
        <div className="h-full flex flex-col relative">
            {/* Header */}
            <div className="flex items-center justify-between mb-6">
                <div>
                    <h1 className="text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
                        <FolderOpen className="h-6 w-6 text-gray-500" /> Vault
                    </h1>
                    <p className="text-gray-600 text-sm mt-0.5">Your cryptographically secure workspace.</p>
                </div>
                <Button variant="neon" onClick={() => setIsUploadModalOpen(true)} className="gap-2">
                    <UploadCloud className="h-4 w-4" /> Upload
                </Button>
            </div>

            {/* Global Search */}
            <GlobalSearch />

            {isLoading ? (
                <div className="flex-1 flex items-center justify-center"><Activity className="h-6 w-6 text-gray-600 animate-spin" /></div>
            ) : (
                <div className="flex-1 overflow-y-auto pr-1 pb-20">
                    {/* Pinned */}
                    <AnimatePresence>
                        {pinnedDocs.length > 0 && (
                            <motion.div
                                initial={{ opacity: 0, height: 0, overflow: 'hidden', paddingBottom: 0 }}
                                animate={{ opacity: 1, height: 'auto', overflow: 'visible', paddingBottom: 32 }}
                                exit={{ opacity: 0, height: 0, overflow: 'hidden', paddingBottom: 0 }}
                                className="mb-0 overflow-hidden"
                            >
                                <div className="flex items-center gap-2 mb-4">
                                    <Star className="h-4 w-4 text-amber-500 fill-amber-500" />
                                    <h2 className="text-lg font-display font-semibold text-white">Pinned</h2>
                                    <span className="bg-amber-500/10 text-amber-400 px-2 py-0.5 rounded text-[11px] font-mono">{pinnedDocs.length}</span>
                                </div>
                                <motion.div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3"
                                    initial="hidden" animate="visible"
                                    variants={{ hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.04 } } }}
                                >
                                    {pinnedDocs.map(renderDocCard)}
                                </motion.div>
                            </motion.div>
                        )}
                    </AnimatePresence>

                    {/* All Documents */}
                    <div className="mb-10">
                        <div className="flex items-center gap-2 mb-4">
                            <h2 className="text-lg font-display font-semibold text-white">
                                {pinnedDocs.length > 0 ? 'All Documents' : 'My Documents'}
                            </h2>
                            <span className="bg-white/[0.06] px-2 py-0.5 rounded text-[11px] text-gray-500 font-mono">{unpinnedDocs.length}</span>
                        </div>
                        {unpinnedDocs.length === 0 && pinnedDocs.length === 0 ? (
                            <div className="flex flex-col items-center justify-center p-16 border border-white/[0.04] bg-white/[0.01] rounded-xl border-dashed">
                                <FolderOpen className="h-10 w-10 text-gray-700 mb-3" />
                                <p className="text-gray-600 text-sm">No documents yet. Upload your first file.</p>
                            </div>
                        ) : unpinnedDocs.length === 0 ? (
                            <div className="flex flex-col items-center justify-center p-10 border border-white/[0.04] bg-white/[0.01] rounded-xl border-dashed">
                                <p className="text-gray-600 text-xs">All documents are pinned.</p>
                            </div>
                        ) : (
                            <motion.div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3"
                                initial="hidden" animate="visible"
                                variants={{ hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.04 } } }}
                            >
                                {unpinnedDocs.map(renderDocCard)}
                            </motion.div>
                        )}
                    </div>
                </div>
            )}

            {/* Drawer */}
            <AnimatePresence>
                {isDrawerOpen && activeDocContext && <DocDrawer doc={activeDocContext} onClose={() => setIsDrawerOpen(false)} user={user} toast={toast} />}
            </AnimatePresence>

            {/* Upload Modal */}
            <AnimatePresence>
                {isUploadModalOpen && (
                    <>
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-black/70 z-50" onClick={() => setIsUploadModalOpen(false)} />
                        <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }} className="fixed inset-0 m-auto w-full max-w-md h-fit z-50 p-4">
                            <Card>
                                <div className="p-6">
                                    <h3 className="text-lg font-display font-bold mb-1 flex items-center gap-2"><Shield className="h-4 w-4 text-red-500" /> Secure Upload</h3>
                                    <p className="text-gray-500 text-xs mb-5">Cryptographically verified and anchored to CoC.</p>
                                    <form onSubmit={handleUpload} className="space-y-4">
                                        <div className="border border-dashed border-white/10 bg-white/[0.01] rounded-lg p-6 text-center hover:bg-red-500/5 hover:border-red-500/40 transition-all duration-300 group cursor-pointer relative shadow-[inset_0_2px_10px_rgba(0,0,0,0.2)]">
                                            <input type="file" required onChange={e => setFileToUpload(e.target.files[0])} className="absolute inset-0 w-full h-full opacity-0 cursor-pointer" />
                                            <UploadCloud className="h-8 w-8 text-gray-600 mx-auto mb-2 group-hover:text-red-500/60 transition-colors" />
                                            <p className="text-xs text-gray-400">{fileToUpload ? fileToUpload.name : "Drop file or browse"}</p>
                                        </div>
                                        <div className="flex justify-end gap-2">
                                            <Button type="button" variant="ghost" onClick={() => setIsUploadModalOpen(false)}>Cancel</Button>
                                            <Button type="submit" disabled={!fileToUpload}>Upload</Button>
                                        </div>
                                    </form>
                                </div>
                            </Card>
                        </motion.div>
                    </>
                )}
            </AnimatePresence>

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

            {/* Delete Confirmation */}
            <AnimatePresence>
                {deleteTarget && (
                    <>
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-black/70 z-50" onClick={() => setDeleteTarget(null)} />
                        <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }} className="fixed inset-0 m-auto w-full max-w-sm h-fit z-50 p-4">
                            <Card>
                                <div className="p-6">
                                    <h3 className="text-lg font-display font-bold mb-1 flex items-center gap-2"><Trash2 className="h-4 w-4 text-red-500" /> Move to Bin</h3>
                                    <p className="text-gray-500 text-xs mb-5">
                                        Move <span className="text-white">{deleteTarget.filename}</span> to recycle bin? All shares will be suspended.
                                    </p>
                                    <div className="flex justify-end gap-2">
                                        <Button variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</Button>
                                        <Button variant="neon" onClick={() => handleDelete(deleteTarget)} className="gap-1">
                                            <Trash2 className="h-3.5 w-3.5" /> Move to Bin
                                        </Button>
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

// ── Document Drawer with Preview + Chat ─────────────────

function DocDrawer({ doc, onClose, user, toast }) {
    const [messages, setMessages] = useState([]);
    const [newMsg, setNewMsg] = useState('');
    const [replyTo, setReplyTo] = useState(null);
    const [ws, setWs] = useState(null);
    const [activeTab, setActiveTab] = useState(canPreview(doc.mime_type) ? 'preview' : 'chat');

    // Preview state
    const [previewContent, setPreviewContent] = useState(null);
    const [previewUrl, setPreviewUrl] = useState(null);
    const [isLoadingPreview, setIsLoadingPreview] = useState(false);

    // Load preview
    useEffect(() => {
        if (activeTab !== 'preview') return;
        if (!canPreview(doc.mime_type)) return;
        setIsLoadingPreview(true);
        (async () => {
            try {
                if (PREVIEW_IMAGE.test(doc.mime_type)) {
                    const res = await axios.get(`/documents/${doc.id}/download`, { responseType: 'blob' });
                    setPreviewUrl(URL.createObjectURL(res.data));
                } else if (PREVIEW_TEXT.test(doc.mime_type)) {
                    const res = await axios.get(`/documents/${doc.id}/download`, { responseType: 'text' });
                    setPreviewContent(res.data);
                } else if (PREVIEW_PDF.test(doc.mime_type)) {
                    const res = await axios.get(`/documents/${doc.id}/download`, { responseType: 'blob' });
                    setPreviewUrl(URL.createObjectURL(res.data));
                }
            } catch { }
            finally { setIsLoadingPreview(false); }
        })();
        return () => { if (previewUrl) URL.revokeObjectURL(previewUrl); };
    }, [activeTab, doc.id]);

    // WebSocket for chat
    useEffect(() => {
        const tokenCookie = document.cookie.split('; ').find(row => row.startsWith('session_token='));
        const token = tokenCookie ? tokenCookie.split('=')[1] : '';
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const host = import.meta.env.DEV ? '127.0.0.1:8100' : location.host;
        const socket = new WebSocket(`${protocol}//${host}/ws/documents/${doc.id}`);
        socket.onopen = () => socket.send(JSON.stringify({ token, type: 'join' }));
        socket.onmessage = (e) => {
            const data = JSON.parse(e.data);
            if (data.type === 'joined') {
                axios.get(`/documents/${doc.id}/messages`).then(r => setMessages(r.data)).catch(() => { });
            } else if (data.type === 'message') {
                setMessages(prev => [...prev, data]);
            }
        };
        setWs(socket);
        return () => socket.close();
    }, [doc.id]);

    const sendMsg = (e) => {
        e.preventDefault();
        if (!newMsg || !ws || ws.readyState !== WebSocket.OPEN) return;
        ws.send(JSON.stringify({ type: 'message', body: newMsg, parent_message_id: replyTo?.id || null }));
        setNewMsg('');
        setReplyTo(null);
    };

    const renderPreview = () => {
        if (isLoadingPreview) return <div className="flex-1 flex items-center justify-center"><Activity className="h-5 w-5 text-gray-600 animate-spin" /></div>;
        if (PREVIEW_IMAGE.test(doc.mime_type) && previewUrl) {
            return <div className="flex-1 flex items-center justify-center p-4 overflow-auto"><img src={previewUrl} alt={doc.filename} className="max-w-full max-h-full rounded-lg object-contain" /></div>;
        }
        if (PREVIEW_TEXT.test(doc.mime_type) && previewContent !== null) {
            return <div className="flex-1 overflow-auto p-4"><pre className="text-xs text-gray-300 font-mono whitespace-pre-wrap break-words bg-white/[0.02] rounded-lg p-4 border border-white/[0.04]">{previewContent}</pre></div>;
        }
        if (PREVIEW_PDF.test(doc.mime_type) && previewUrl) {
            return <div className="flex-1 overflow-hidden"><embed src={previewUrl} type="application/pdf" className="w-full h-full" /></div>;
        }
        return (
            <div className="flex-1 flex flex-col items-center justify-center opacity-30">
                <FileText className="h-8 w-8 mb-2" />
                <p className="text-xs">Preview not available for this file type.</p>
                <p className="text-[10px] text-gray-600 mt-1">{doc.mime_type}</p>
            </div>
        );
    };

    return (
        <>
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-black/30 z-40 lg:hidden" onClick={onClose} />
            <motion.div
                initial={{ x: '100%' }} animate={{ x: 0 }} exit={{ x: '100%' }}
                transition={{ type: "spring", damping: 28, stiffness: 250 }}
                className="fixed top-0 right-0 h-full w-full max-w-sm bg-[#050505] border-l border-white/[0.06] z-50 flex flex-col"
            >
                {/* Header */}
                <div className="p-4 border-b border-white/[0.06] flex items-center justify-between">
                    <div className="flex flex-col">
                        <span className="font-medium text-sm text-white truncate max-w-[220px]">{doc.filename}</span>
                        <span className="text-[10px] text-gray-600 flex items-center gap-1 font-mono"><Hash className="h-2.5 w-2.5" />{doc.coc_node_hash?.substring(0, 10)}</span>
                    </div>
                    <Button variant="ghost" size="icon" onClick={onClose} className="h-7 w-7"><X className="h-3.5 w-3.5" /></Button>
                </div>

                {/* Tabs */}
                <div className="flex border-b border-white/[0.04] px-4">
                    {canPreview(doc.mime_type) && (
                        <button onClick={() => setActiveTab('preview')}
                            className={`px-3 py-2.5 text-xs font-medium border-b-2 transition-colors ${activeTab === 'preview' ? 'text-white border-red-500' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
                            <Eye className="h-3 w-3 inline mr-1" />Preview
                        </button>
                    )}
                    <button onClick={() => setActiveTab('chat')}
                        className={`px-3 py-2.5 text-xs font-medium border-b-2 transition-colors ${activeTab === 'chat' ? 'text-white border-red-500' : 'text-gray-500 border-transparent hover:text-gray-300'}`}>
                        <MessageSquare className="h-3 w-3 inline mr-1" />Chat
                    </button>
                </div>

                {/* Tab Content */}
                <div className="flex-1 overflow-hidden relative flex flex-col">
                    {activeTab === 'preview' ? renderPreview() : (
                        <div className="h-full flex flex-col">
                            <div className="flex-1 overflow-y-auto p-4 space-y-4">
                                {messages.length === 0 ? (
                                    <div className="h-full flex flex-col items-center justify-center opacity-30">
                                        <MessageSquare className="h-6 w-6 mb-2" /><p className="text-sm">No messages yet.</p>
                                    </div>
                                ) : messages.map((m, i) => {
                                    const isMe = m.sender_username === user?.username || m.sender === user?.username;
                                    const isReply = Boolean(m.parent_message_id);
                                    return (
                                        <div key={i} className={`flex flex-col max-w-[85%] ${isMe ? 'self-end items-end ml-auto' : 'self-start items-start'} ${isReply ? 'ml-6 border-l-2 border-white/10 pl-2' : ''}`}>
                                            <span className="text-[10px] text-gray-500 mb-1 px-1">{m.sender_username || m.sender}</span>
                                            <div className={`px-4 py-2.5 rounded-2xl text-[13px] shadow-sm ${isMe ? 'bg-red-600/90 text-white rounded-tr-sm shadow-red-900/20' : 'bg-white/[0.08] text-gray-200 rounded-tl-sm border border-white/[0.05]'}`}>
                                                {m.body}
                                            </div>
                                            <button type="button" onClick={() => setReplyTo(m)} className="text-[10px] text-gray-500 mt-1 hover:text-white transition-colors">Reply</button>
                                        </div>
                                    );
                                })}
                            </div>
                            <div className="p-4 border-t border-white/[0.04] bg-gradient-to-t from-[#020202] to-transparent sticky bottom-0 z-10 w-full">
                                {replyTo && (
                                    <div className="text-[10px] text-gray-400 mb-2 flex items-center justify-between bg-white/[0.04] px-3 py-2 rounded-lg border border-white/[0.04] shadow-[0_4px_12px_rgba(0,0,0,0.5)]">
                                        <div className="flex items-center gap-2 truncate">
                                            <div className="h-4 w-1 bg-white/20 rounded-full" />
                                            <span className="truncate">Replying to <span className="text-gray-200 font-medium">{replyTo.sender_username || replyTo.sender}</span></span>
                                        </div>
                                        <button type="button" onClick={() => setReplyTo(null)} className="text-gray-500 hover:text-white bg-white/[0.05] hover:bg-white/[0.1] rounded-full p-1 transition-colors"><X className="h-3 w-3" /></button>
                                    </div>
                                )}
                                <form onSubmit={sendMsg} className="flex gap-2 items-center bg-white/[0.02] border border-white/[0.06] p-1 rounded-full shadow-[0_8px_30px_rgba(0,0,0,0.4)] focus-within:border-white/[0.1] focus-within:bg-white/[0.04] transition-all">
                                    <Input
                                        className="flex-1 h-10 bg-transparent border-0 ring-0 focus-visible:ring-0 focus-visible:border-0 px-4 text-sm font-medium text-gray-200 placeholder:text-gray-600 placeholder:font-normal"
                                        placeholder="Secure message..."
                                        value={newMsg}
                                        onChange={e => setNewMsg(e.target.value)}
                                    />
                                    <Button
                                        type="submit"
                                        className={`rounded-full shrink-0 h-10 w-10 p-0 transition-all duration-300 ${newMsg ? 'bg-red-500 hover:bg-red-400 text-white shadow-[0_0_15px_rgba(255,7,58,0.4)]' : 'bg-white/5 text-gray-600 hover:bg-white/10'}`}
                                        disabled={!newMsg}
                                    >
                                        <ChevronRight className="h-5 w-5 ml-0.5" />
                                    </Button>
                                </form>
                            </div>
                        </div>
                    )}
                </div>
            </motion.div>
        </>
    );
}
