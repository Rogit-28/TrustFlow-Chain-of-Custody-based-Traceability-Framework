import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { useToast } from '../components/ui/toast';
import { Search, ShieldAlert, CheckCircle2, XCircle, Info, Lock, Fingerprint, Activity, Code, Bug } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

export default function LeakDetectionView() {
    const [leakContent, setLeakContent] = useState('');
    const [isDetecting, setIsDetecting] = useState(false);
    const [leakResult, setLeakResult] = useState(null);
    const [analysisSteps, setAnalysisSteps] = useState([]);
    const toast = useToast();

    const handleDetect = async (e) => {
        e.preventDefault();
        if (!leakContent.trim()) return;

        setIsDetecting(true);
        setLeakResult(null);
        setAnalysisSteps([]);

        try {
            // Simulate stepping animation for analysis process
            setAnalysisSteps(['Initializing steganographic parser...']);
            await new Promise(r => setTimeout(r, 600));
            setAnalysisSteps(prev => [...prev, 'Scanning for Zero-Width Character (ZWC) anomalies...']);
            await new Promise(r => setTimeout(r, 800));

            const res = await axios.post('/admin/detect-leak', { content: leakContent });

            if (res.data.leak_detected) {
                setAnalysisSteps(prev => [...prev, `Detected ZWC block. Algorithm: ${res.data.method}`]);
                await new Promise(r => setTimeout(r, 700));
                setAnalysisSteps(prev => [...prev, 'Decrypting embedded peer attribution signature...']);
                await new Promise(r => setTimeout(r, 600));
                setAnalysisSteps(prev => [...prev, 'Verification successful. Establishing chain identity.']);
            } else {
                setAnalysisSteps(prev => [...prev, 'No ZWC blocks found in sample.']);
                await new Promise(r => setTimeout(r, 500));
                setAnalysisSteps(prev => [...prev, 'Attempting statistical fallback analysis...']);
                await new Promise(r => setTimeout(r, 600));
                setAnalysisSteps(prev => [...prev, 'Analysis complete. Clean content.']);
            }

            setLeakResult(res.data);
        } catch (err) {
            toast({ title: 'Detection failed', description: err.message, type: 'error' });
        } finally {
            setIsDetecting(false);
        }
    };

    return (
        <div className="min-h-full flex flex-col w-full space-y-6 lg:space-y-8">
            <div className="flex items-center gap-3 shrink-0">
                <Search className="h-7 w-7 text-red-500" />
                <div>
                    <h1 className="text-2xl font-display font-bold text-white tracking-tight">Leak Detection</h1>
                    <p className="text-gray-500 text-sm mt-0.5">Steganographic watermark extraction & peer attribution.</p>
                </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch flex-1 pb-6">

                {/* Input Pane */}
                <Card className="flex flex-col h-full border-white/[0.06] bg-[#050505]">
                    <CardHeader className="pb-3 border-b border-white/[0.04]">
                        <CardTitle className="text-base flex items-center gap-2">
                            <Bug className="h-4 w-4 text-red-500" /> Suspicious Content
                        </CardTitle>
                        <CardDescription>Paste the leaked text you found in the wild below.</CardDescription>
                    </CardHeader>
                    <CardContent className="flex-1 p-4 flex flex-col gap-3">
                        <textarea
                            className="w-full flex-1 min-h-[240px] bg-[#0a0a0a] border border-white/[0.08] shadow-inner rounded-xl p-4 text-sm text-gray-300 resize-none placeholder:text-gray-700 focus:outline-none focus:ring-1 focus:ring-red-500/40 focus:border-red-500/30 font-mono transition-all"
                            placeholder={"Paste leaked content here...\n\nExample:\nConfidential Report \u200b\u200c Q3 Earnings..."}
                            value={leakContent}
                            onChange={(e) => setLeakContent(e.target.value)}
                        />
                        <div className="flex items-center justify-between mt-2">
                            <span className="text-xs text-gray-600 font-mono">{leakContent.length} chars</span>
                            <Button
                                onClick={handleDetect}
                                disabled={isDetecting || !leakContent.trim()}
                                variant="neon"
                                className="px-6"
                            >
                                {isDetecting ? <Activity className="h-4 w-4 animate-spin mr-2" /> : <Search className="h-4 w-4 mr-2" />}
                                {isDetecting ? 'Analyzing...' : 'Analyze Payload'}
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                {/* Output / Analysis Pane */}
                <Card className="flex flex-col h-full border-white/[0.06] bg-black shadow-2xl relative overflow-hidden">
                    <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-red-500/20 to-transparent" />

                    <CardHeader className="pb-3 border-b border-white/[0.04] bg-[#050505]">
                        <CardTitle className="text-base flex items-center gap-2">
                            <Activity className="h-4 w-4 text-emerald-500" /> Forensic Terminal
                        </CardTitle>
                    </CardHeader>

                    <CardContent className="flex-1 p-0 flex flex-col">

                        {/* Status Console (Top half) */}
                        <div className="bg-[#050505] min-h-[140px] p-5 border-b border-white/[0.04] font-mono text-xs flex flex-col justify-end">
                            {analysisSteps.length === 0 && !leakResult && (
                                <div className="text-gray-700 text-center pb-4">Awaiting input...</div>
                            )}
                            <AnimatePresence>
                                {analysisSteps.map((step, idx) => (
                                    <motion.div
                                        key={idx}
                                        initial={{ opacity: 0, x: -10 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        className="text-gray-400 mb-1 flex items-start gap-2"
                                    >
                                        <span className="text-red-500/50">›</span> {step}
                                    </motion.div>
                                ))}
                            </AnimatePresence>
                        </div>

                        {/* Culprit Reveal (Bottom half) */}
                        <div className="flex-1 p-6 relative flex flex-col items-center justify-center min-h-[160px]">
                            <AnimatePresence mode="wait">
                                {isDetecting ? (
                                    <motion.div
                                        key="loading"
                                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                                        className="flex flex-col items-center justify-center opacity-50"
                                    >
                                        <div className="h-16 w-16 mb-4 relative flex items-center justify-center">
                                            <div className="absolute inset-0 rounded-full border-2 border-red-500/20 border-t-red-500 animate-spin" />
                                            <Search className="h-6 w-6 text-red-500/50" />
                                        </div>
                                        <div className="text-xs text-gray-600 uppercase tracking-widest font-bold">Scanning...</div>
                                    </motion.div>
                                ) : leakResult ? (
                                    leakResult.leak_detected ? (
                                        <motion.div
                                            key="found"
                                            initial={{ opacity: 0, scale: 0.9, y: 10 }}
                                            animate={{ opacity: 1, scale: 1, y: 0 }}
                                            transition={{ type: 'spring', damping: 20 }}
                                            className="w-full h-full flex flex-col items-center justify-center bg-red-500/5 border border-red-500/20 rounded-xl p-6 relative overflow-hidden"
                                        >
                                            <div className="absolute inset-x-0 -top-px h-px bg-gradient-to-r from-transparent via-red-500 to-transparent" />
                                            <ShieldAlert className="h-10 w-10 text-red-500 mb-3 drop-shadow-[0_0_10px_rgba(255,7,58,0.5)]" />
                                            <h3 className="text-red-400 font-bold uppercase tracking-widest text-xs mb-4">Culprit Identified</h3>

                                            <div className="flex flex-col items-center gap-1 mb-6 w-full">
                                                <div className="text-xs text-gray-500 font-mono">Decrypted Peer ID:</div>
                                                <div className="text-xl md:text-2xl font-mono text-white tracking-wider cursor-text select-all bg-black/50 px-4 py-2 rounded border border-white/10 w-max max-w-full truncate">
                                                    {leakResult.suspected_peer_id}
                                                </div>
                                            </div>

                                            <div className="flex items-center gap-8 text-xs font-mono">
                                                <div className="flex flex-col items-center gap-1">
                                                    <span className="text-gray-500">Confidence</span>
                                                    <span className="text-emerald-400 font-bold">{(leakResult.confidence * 100).toFixed(1)}%</span>
                                                </div>
                                                <div className="flex flex-col items-center gap-1">
                                                    <span className="text-gray-500">Method</span>
                                                    <span className="text-white bg-white/10 px-1.5 rounded">{leakResult.method}</span>
                                                </div>
                                            </div>
                                        </motion.div>
                                    ) : (
                                        <motion.div
                                            key="clean"
                                            initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }}
                                            className="w-full h-full flex flex-col items-center justify-center bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-6 text-center"
                                        >
                                            <CheckCircle2 className="h-10 w-10 text-emerald-500 mb-3 drop-shadow-[0_0_10px_rgba(16,185,129,0.3)]" />
                                            <h3 className="text-emerald-400 font-bold uppercase tracking-widest text-xs mb-2">Clean Content</h3>
                                            <p className="text-sm text-gray-400">No cryptographic watermarks found. This text was either not generated by TrustDocs or the watermarks were cleanly stripped.</p>
                                        </motion.div>
                                    )
                                ) : null}
                            </AnimatePresence>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Educational Section */}
            <Card className="bg-[#050505] border-white/[0.06] overflow-hidden relative shrink-0">
                <div className="absolute top-0 right-0 w-64 h-64 bg-red-500/5 blur-3xl pointer-events-none rounded-full -translate-y-1/2 translate-x-1/2" />
                <CardContent className="p-6 md:p-8">
                    <div className="flex flex-col md:flex-row gap-8 items-start">
                        <div className="flex-1 space-y-4 text-sm text-gray-400 leading-relaxed">
                            <h3 className="text-lg font-display font-semibold text-white flex items-center gap-2 mb-2">
                                <Fingerprint className="h-5 w-5 text-emerald-500" />
                                Invisible Tracers
                            </h3>
                            <p>
                                When a document is shared within TrustDocs, it is uniquely watermarked with <strong className="text-gray-200">Zero-Width Characters (ZWCs)</strong>—specifically <code className="bg-white/10 px-1 py-0.5 rounded text-white text-xs">U+200B</code> (Zero-Width Space) and <code className="bg-white/10 px-1 py-0.5 rounded text-white text-xs">U+200C</code> (Zero-Width Non-Joiner).
                            </p>
                            <p>
                                These characters are cryptographically embedded into standard whitespace (like spaces and line breaks) representing binary <code className="text-red-400 font-mono">0</code>s and <code className="text-red-400 font-mono">1</code>s. This creates an invisible payload containing the recipient's unique Peer ID.
                            </p>
                            <p>
                                If an authorized user copies the secure document and pastes it elsewhere (like a public forum, email, or chat application), the invisible payload is carried over with the text. We can extract this payload to attribute the leak directly to the responsible party.
                            </p>
                        </div>

                        <div className="w-full md:w-80 bg-black/40 border border-white/[0.04] p-4 rounded-xl flex flex-col gap-3 font-mono text-[10px] shrink-0">
                            <div className="text-gray-500 mb-1 border-b border-white/[0.04] pb-2 flex items-center justify-between">
                                <span>Encoding Process</span>
                                <Code className="h-3 w-3" />
                            </div>
                            <div>
                                <div className="text-emerald-500/70 mb-0.5">Input Text:</div>
                                <div className="text-gray-300 bg-white/5 p-1.5 rounded">"Project Orion"</div>
                            </div>
                            <div>
                                <div className="text-emerald-500/70 mb-0.5 z-10">ZWC Binary Payload (PeerID):</div>
                                <div className="text-red-400/80 break-all leading-tight">10110010 01001101</div>
                            </div>
                            <div>
                                <div className="text-emerald-500/70 mb-0.5">Watermarked Text:</div>
                                <div className="text-white bg-red-500/10 p-1.5 rounded relative group">
                                    "Project<span className="text-red-500 font-bold opacity-0 group-hover:opacity-100 transition-opacity">_</span>Orion"
                                    <div className="absolute inset-x-0 -bottom-6 text-center text-[9px] text-red-400 opacity-0 group-hover:opacity-100 transition-opacity">Hover to reveal ZWCs</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </CardContent>
            </Card>

        </div>
    );
}
