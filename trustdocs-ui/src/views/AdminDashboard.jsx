import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useToast } from '../components/ui/toast';
import { Shield, Network, Activity, Search, ShieldAlert, CheckCircle2, XCircle, FileText, Share2, Info, Maximize2, Minimize2 } from 'lucide-react';
import { Network as VisNetwork } from 'vis-network';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

export default function AdminDashboard() {
    const [peers, setPeers] = useState([]);
    const [auditResult, setAuditResult] = useState(null);
    const [leakContent, setLeakContent] = useState('');
    const [leakResult, setLeakResult] = useState(null);
    const [isVerifying, setIsVerifying] = useState(false);
    const [isDetecting, setIsDetecting] = useState(false);
    const [activeGraph, setActiveGraph] = useState('my');
    const [documents, setDocuments] = useState([]);
    const [selectedDoc, setSelectedDoc] = useState('');
    const [selectedDocName, setSelectedDocName] = useState('');
    const [isFullscreen, setIsFullscreen] = useState(false);

    // File Trace search state
    const [fileSearchQuery, setFileSearchQuery] = useState('');
    const [showFilePicker, setShowFilePicker] = useState(false);
    const fileSearchRef = useRef(null);

    const graphRef = useRef(null);
    const networkRef = useRef(null);
    const toast = useToast();

    const fetchPeers = async () => { try { const res = await axios.get('/admin/peers'); setPeers(res.data); } catch { } };

    const fetchDocuments = async () => {
        try {
            const res = await axios.get('/documents');
            // Only include docs with shares for File Trace
            const owned = res.data.owned || [];
            setDocuments(owned);
        } catch { }
    };

    const sharedDocs = documents.filter(d => d.share_count > 0);
    const filteredDocs = fileSearchQuery.trim()
        ? sharedDocs.filter(d => d.filename.toLowerCase().includes(fileSearchQuery.toLowerCase()))
        : sharedDocs;

    const loadGraph = async () => {
        try {
            const endpoint = activeGraph === 'my' ? '/admin/graph/me' : `/documents/${selectedDoc}/trace`;
            if (activeGraph === 'file' && !selectedDoc) return;
            const res = await axios.get(endpoint);
            const { nodes, edges } = res.data;

            const vNodes = nodes.map(n => ({
                id: n.node_hash,
                label: n.parent_hash
                    ? `${n.owner_username}\n${n.node_hash.substring(0, 6)}`
                    : `${n.owner_username}\n${n.filename ? n.filename.substring(0, 15) + '…' : ''}\n${n.node_hash.substring(0, 6)}`,
                color: {
                    background: n.is_online ? 'rgba(16,185,129,0.1)' : (n.parent_hash ? 'rgba(255,255,255,0.04)' : 'rgba(255,7,58,0.08)'),
                    border: n.is_online ? '#10b981' : (n.parent_hash ? 'rgba(255,255,255,0.2)' : '#ff073a'),
                    highlight: { background: n.is_online ? 'rgba(16,185,129,0.2)' : 'rgba(255,7,58,0.15)', border: n.is_online ? '#10b981' : '#ff073a' },
                    hover: { background: n.is_online ? 'rgba(16,185,129,0.15)' : 'rgba(255,7,58,0.1)', border: n.is_online ? '#10b981' : '#ff073a' }
                },
                font: { color: n.is_online ? '#10b981' : '#999', face: 'Inter', size: 10 },
                shape: n.parent_hash ? 'dot' : 'diamond',
                size: n.parent_hash ? 12 : 22,
                shadow: { enabled: true, color: n.is_online ? 'rgba(16,185,129,0.4)' : (n.parent_hash ? 'rgba(255,255,255,0.05)' : 'rgba(255,7,58,0.3)'), size: 12 },
                borderWidth: n.parent_hash ? 1 : 2
            }));

            const vEdges = edges.map((e, i) => ({
                id: i, from: e.from, to: e.to, arrows: 'to',
                color: { color: 'rgba(255,255,255,0.08)', highlight: '#ff073a', hover: 'rgba(255,7,58,0.3)' },
                smooth: { type: 'curvedCW', roundness: 0.15 },
                width: 1
            }));

            if (networkRef.current) {
                networkRef.current.setData({ nodes: vNodes, edges: vEdges });
            } else if (graphRef.current) {
                networkRef.current = new VisNetwork(graphRef.current, { nodes: vNodes, edges: vEdges }, {
                    physics: { solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -50, springLength: 100 } },
                    interaction: { hover: true, tooltipDelay: 200 }
                });
            }
        } catch { toast({ title: 'Graph load failed', type: 'error' }); }
    };

    useEffect(() => { fetchPeers(); fetchDocuments(); }, []);
    useEffect(() => { if (activeGraph === 'my' || selectedDoc) loadGraph(); }, [activeGraph, selectedDoc]);

    // Close file picker on outside click
    useEffect(() => {
        const handler = (e) => { if (fileSearchRef.current && !fileSearchRef.current.contains(e.target)) setShowFilePicker(false); };
        document.addEventListener('mousedown', handler);
        return () => document.removeEventListener('mousedown', handler);
    }, []);

    const handleVerify = async () => {
        setIsVerifying(true);
        try { const res = await axios.post('/admin/verify-log'); setAuditResult(res.data); }
        catch { toast({ title: 'Verify failed', type: 'error' }); }
        finally { setIsVerifying(false); }
    };

    const handleDetect = async (e) => {
        e.preventDefault(); if (!leakContent) return;
        setIsDetecting(true);
        try { const res = await axios.post('/admin/detect-leak', { content: leakContent }); setLeakResult(res.data); }
        catch { toast({ title: 'Detection failed', type: 'error' }); }
        finally { setIsDetecting(false); }
    };

    const selectFileForTrace = (doc) => {
        setSelectedDoc(doc.id);
        setSelectedDocName(doc.filename);
        setShowFilePicker(false);
        setFileSearchQuery('');
    };

    return (
        <div className="h-full flex flex-col">
            <div className="mb-8 flex items-center gap-3">
                <ShieldAlert className="h-6 w-6 text-red-500" />
                <div>
                    <h1 className="text-2xl font-display font-bold text-white tracking-tight">Mission Control</h1>
                    <p className="text-gray-600 text-sm mt-0.5">Network topography and forensic analysis.</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 flex-1 pb-8 overflow-y-auto pr-1">
                {/* Graph */}
                <Card className={`flex flex-col transition-all duration-300 ${isFullscreen ? 'fixed inset-4 z-[100] shadow-2xl bg-black rounded-lg border border-white/[0.1]' : 'lg:col-span-2'}`}>
                    <CardHeader className="border-b border-white/[0.04] pb-4">
                        <div className="flex justify-between items-center">
                            <div>
                                <CardTitle className="text-base flex items-center gap-2"><Network className="h-4 w-4 text-gray-500" /> CoC Topography</CardTitle>
                                <CardDescription>Provenance tree of all digital assets.</CardDescription>
                            </div>
                            <div className="flex items-center gap-2">
                                <Button onClick={() => setIsFullscreen(!isFullscreen)} size="sm" variant="ghost" className="px-2">
                                    {isFullscreen ? <Minimize2 className="h-4 w-4 text-gray-400" /> : <Maximize2 className="h-4 w-4 text-gray-400" />}
                                </Button>
                                <Button onClick={loadGraph} size="sm" variant="secondary">Refresh</Button>
                            </div>
                        </div>
                        <div className="flex items-center gap-1 mt-3 bg-[#050505] p-1 rounded-lg w-max border border-white/[0.04] shadow-inner">
                            <Button size="sm" variant={activeGraph === 'my' ? 'secondary' : 'ghost'} onClick={() => { setActiveGraph('my'); setSelectedDoc(''); setSelectedDocName(''); }} className={`px-4 rounded-md transition-all duration-300 ${activeGraph === 'my' ? 'bg-white/[0.08] shadow-[0_2px_10px_rgba(0,0,0,0.5)] border border-white/10' : 'hover:bg-white/[0.03] text-gray-500'}`}>My Network</Button>
                            <Button size="sm" variant={activeGraph === 'file' ? 'secondary' : 'ghost'} onClick={() => { setActiveGraph('file'); setSelectedDoc(''); setSelectedDocName(''); if (networkRef.current) networkRef.current.setData({ nodes: [], edges: [] }); }} className={`px-4 rounded-md transition-all duration-300 ${activeGraph === 'file' ? 'bg-white/[0.08] shadow-[0_2px_10px_rgba(0,0,0,0.5)] border border-white/10' : 'hover:bg-white/[0.03] text-gray-500'}`}>File Trace</Button>
                        </div>

                        {/* File Trace: Search picker */}
                        <AnimatePresence mode="wait">
                            {activeGraph === 'file' && (
                                <motion.div
                                    key="file-trace-picker"
                                    initial={{ opacity: 0, marginTop: 0 }}
                                    animate={{ opacity: 1, marginTop: 12 }}
                                    exit={{ opacity: 0, marginTop: 0 }}
                                    transition={{ duration: 0.2 }}
                                    className="relative z-20"
                                >
                                    {sharedDocs.length === 0 ? (
                                        <div className="flex items-center gap-2 p-3 border border-white/[0.04] rounded-lg bg-white/[0.01]">
                                            <Share2 className="h-4 w-4 text-gray-600" />
                                            <p className="text-xs text-gray-500">No shared files to trace. Share a document first to see its trace.</p>
                                        </div>
                                    ) : (
                                        <div ref={fileSearchRef} className="relative">
                                            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-600" />
                                            <input
                                                type="text"
                                                placeholder={selectedDocName || "Search shared files to trace..."}
                                                value={fileSearchQuery}
                                                onChange={(e) => { setFileSearchQuery(e.target.value); setShowFilePicker(true); }}
                                                onFocus={() => setShowFilePicker(true)}
                                                className="w-full pl-9 pr-3 py-2 bg-white/[0.03] border border-white/[0.06] rounded-lg text-xs text-white placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-red-500/30 transition-all"
                                            />
                                            <AnimatePresence>
                                                {showFilePicker && (
                                                    <motion.div
                                                        initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                                                        className="absolute top-full mt-1 w-full bg-[#0a0a0a] border border-white/[0.08] rounded-lg shadow-2xl z-30 max-h-48 overflow-y-auto"
                                                    >
                                                        {filteredDocs.length === 0 ? (
                                                            <div className="px-4 py-3 text-xs text-gray-500">No matching shared files.</div>
                                                        ) : filteredDocs.map((doc) => (
                                                            <button
                                                                key={doc.id}
                                                                onClick={() => selectFileForTrace(doc)}
                                                                className={`w-full flex items-center gap-3 px-4 py-2.5 hover:bg-white/[0.04] transition-colors text-left border-b border-white/[0.04] last:border-b-0 cursor-pointer ${doc.id === selectedDoc ? 'bg-white/[0.04]' : ''}`}
                                                            >
                                                                <FileText className="h-3.5 w-3.5 text-gray-500 shrink-0" />
                                                                <div className="min-w-0 flex-1">
                                                                    <div className="text-xs text-gray-200 truncate">{doc.filename}</div>
                                                                </div>
                                                                <span className="text-[10px] text-gray-600 font-mono shrink-0 flex items-center gap-1">
                                                                    <Share2 className="h-2.5 w-2.5" />{doc.share_count}
                                                                </span>
                                                            </button>
                                                        ))}
                                                    </motion.div>
                                                )}
                                            </AnimatePresence>
                                        </div>
                                    )}
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </CardHeader>
                    <CardContent className="flex-1 p-0 relative min-h-[350px] bg-black isolate">
                        <div ref={graphRef} className="absolute inset-0 w-full h-full -z-10" />
                        {activeGraph === 'file' && !selectedDoc && (
                            <div className="absolute inset-0 bg-black/90 flex flex-col items-center justify-center z-10 transition-colors">
                                <Network className="h-8 w-8 text-gray-700 mb-2" />
                                <p className="text-xs text-gray-600">Select a shared file above to view its trace.</p>
                            </div>
                        )}
                    </CardContent>
                    <CardContent className="border-t border-white/[0.04] py-3 text-[10px] text-gray-500 flex items-center gap-4">
                        <div className="flex items-center gap-1"><span className="h-2 w-2 bg-red-500 rounded-full" /> Root</div>
                        <div className="flex items-center gap-1"><span className="h-2 w-2 bg-white/40 rounded-full" /> Share</div>
                        <div className="flex items-center gap-1"><span className="h-2 w-2 bg-emerald-500 rounded-full" /> Online</div>
                        <div className="flex items-center gap-1"><span className="h-2 w-2 bg-gray-500 rounded-full" /> Offline</div>
                    </CardContent>
                </Card>

                <div className="flex flex-col gap-4">


                    {/* Audit */}
                    <Card className="overflow-visible">
                        <CardHeader className="pb-2 relative">
                            <CardTitle className="text-sm flex items-center gap-2 group cursor-help w-max">
                                <Shield className="h-3.5 w-3.5 text-white/60" /> Immutability Audit
                                <Info className="h-3 w-3 text-gray-500 group-hover:text-white transition-colors" />
                                <div className="absolute top-10 left-6 right-6 p-4 bg-black/80 backdrop-blur-xl border border-white/[0.12] text-xs leading-relaxed text-gray-300 rounded-xl opacity-0 invisible translate-y-2 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 transition-all duration-300 ease-out z-[60] shadow-[0_12px_40px_rgba(0,0,0,0.6)] ring-1 ring-white/[0.02] pointer-events-none">
                                    <div className="flex items-center gap-2 mb-1.5 text-white font-medium tracking-wide">
                                        <Shield className="h-3 w-3 text-emerald-400" /> Audit Mechanism
                                    </div>
                                    Verifies the cryptographic hash chain of the entire global event log (uploads, shares, deletes) to comprehensively detect tampering or revision.
                                </div>
                            </CardTitle>
                            <CardDescription>Verify the hash chain integrity.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Button onClick={handleVerify} isLoading={isVerifying} className="w-full mb-3" variant="secondary">Validate Chain</Button>
                            {auditResult && (
                                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                                    className={`p-3 rounded-lg border flex items-start gap-2 backdrop-blur-xl transition-all duration-500 ${auditResult.valid ? 'border-emerald-500/30 bg-emerald-500/5 shadow-[0_0_15px_rgba(16,185,129,0.15)] ring-1 ring-emerald-500/10' : 'border-red-500/30 bg-red-500/5 shadow-[0_0_15px_rgba(255,7,58,0.15)] ring-1 ring-red-500/10'}`}>
                                    {auditResult.valid ? <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" /> : <XCircle className="h-4 w-4 text-red-500 shrink-0" />}
                                    <div>
                                        <h4 className={`text-xs font-semibold ${auditResult.valid ? 'text-emerald-300' : 'text-red-400'}`}>{auditResult.valid ? 'Verified' : 'Tampered'}</h4>
                                        <p className="text-[10px] text-gray-500 mt-0.5">{auditResult.chain_length} blocks.</p>
                                    </div>
                                </motion.div>
                            )}
                        </CardContent>
                    </Card>

                    {/* Leak Detection */}
                    <Card className="flex-1 overflow-visible">
                        <CardHeader className="pb-2 relative">
                            <CardTitle className="text-sm flex items-center gap-2 group cursor-help w-max">
                                <Search className="h-3.5 w-3.5 text-red-500/60" /> Leak Detection
                                <Info className="h-3 w-3 text-gray-500 group-hover:text-white transition-colors" />
                                <div className="absolute top-10 left-6 right-6 p-4 bg-black/80 backdrop-blur-xl border border-white/[0.12] text-xs leading-relaxed text-gray-300 rounded-xl opacity-0 invisible translate-y-2 group-hover:opacity-100 group-hover:visible group-hover:translate-y-0 transition-all duration-300 ease-out z-[60] shadow-[0_12px_40px_rgba(0,0,0,0.6)] ring-1 ring-white/[0.02] pointer-events-none">
                                    <div className="flex items-center gap-2 mb-1.5 text-white font-medium tracking-wide">
                                        <Search className="h-3 w-3 text-red-500" /> Steganographic Analysis
                                    </div>
                                    Analyze leaked file contents. Extracts invisible zero-width character watermarks to trace the precise user who leaked the document.
                                </div>
                            </CardTitle>
                            <CardDescription>Extract steganographic watermarks.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <form onSubmit={handleDetect} className="flex flex-col gap-2">
                                <textarea
                                    className="w-full h-20 bg-white/[0.03] border border-white/[0.06] rounded-lg p-2 text-xs text-white resize-none placeholder:text-gray-600 focus:outline-none focus:ring-1 focus:ring-red-500/30"
                                    placeholder="Paste leaked content..."
                                    value={leakContent} onChange={e => setLeakContent(e.target.value)} required
                                />
                                <Button type="submit" isLoading={isDetecting} variant="neon">Analyze</Button>
                            </form>
                            {leakResult && (
                                <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                                    className={`mt-3 p-3 rounded-lg border ${leakResult.leak_detected ? 'border-red-500/30 bg-red-500/5 shadow-[0_0_15px_rgba(255,7,58,0.1)]' : 'border-white/[0.06] bg-white/[0.02]'}`}>
                                    {leakResult.leak_detected ? (
                                        <>
                                            <div className="flex items-center gap-1.5 text-red-500 font-semibold text-xs mb-1"><ShieldAlert className="h-3.5 w-3.5" /> Source Identified</div>
                                            <div className="text-[10px] text-gray-400">Suspect: <span className="font-mono text-red-400">{leakResult.suspected_peer_id?.substring(0, 8)}</span></div>
                                            <div className="text-[10px] text-gray-400 mt-0.5">Confidence: {(leakResult.confidence * 100).toFixed(1)}%</div>
                                        </>
                                    ) : (
                                        <div className="flex items-center gap-1.5 text-gray-500 text-xs"><CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" /> No watermarks found.</div>
                                    )}
                                </motion.div>
                            )}
                        </CardContent>
                    </Card>
                </div>
            </div>
        </div>
    );
}
