import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { useToast } from '../components/ui/toast';
import { Users, FileText, Upload, CheckCircle2, Lock, Unlock, ArrowLeft, Shield, Clock, AlertTriangle, Fingerprint } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

export default function BoardroomDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const toast = useToast();

    const [boardroom, setBoardroom] = useState(null);
    const [proposals, setProposals] = useState([]);
    const [isLoading, setIsLoading] = useState(true);

    const [isProposing, setIsProposing] = useState(false);
    const [newTitle, setNewTitle] = useState('');
    const [newContent, setNewContent] = useState('');
    const [enableTimelock, setEnableTimelock] = useState(false);
    const [tlHours, setTlHours] = useState(0);
    const [tlMins, setTlMins] = useState(30);
    const [tlSecs, setTlSecs] = useState(0);
    const [tlPreset, setTlPreset] = useState('30m');

    const [unlockedDoc, setUnlockedDoc] = useState(null); // {title, content, watermarked, timelock_remaining_seconds}

    useEffect(() => {
        fetchData();
        const interval = setInterval(fetchData, 5000);
        return () => clearInterval(interval);
    }, [id]);

    const fetchData = async () => {
        try {
            const brRes = await axios.get('/boardrooms');
            const foundBr = brRes.data.boardrooms.find(b => b.id === id);
            if (!foundBr) {
                navigate('/boardroom');
                return;
            }
            setBoardroom(foundBr);

            const propRes = await axios.get(`/boardrooms/${id}/proposals`);
            setProposals(propRes.data.proposals ? propRes.data.proposals.reverse() : []);
        } catch (err) {
            console.error(err);
        } finally {
            setIsLoading(false);
        }
    };

    const handlePropose = async (e) => {
        e.preventDefault();
        try {
            const payload = {
                title: newTitle,
                content: newContent,
            };
            if (enableTimelock) {
                const totalSecs = (tlHours * 3600) + (tlMins * 60) + tlSecs;
                if (totalSecs >= 60) {
                    payload.ttl_seconds = totalSecs;
                }
            }
            await axios.post(`/boardrooms/${id}/proposals`, payload);
            toast({ title: 'Proposal Initiated', description: 'Document cryptographically split into shares.', type: 'success' });
            setIsProposing(false);
            setNewTitle('');
            setNewContent('');
            setEnableTimelock(false);
            setTlHours(0);
            setTlMins(30);
            setTlSecs(0);
            setTlPreset('30m');
            fetchData();
        } catch (err) {
            toast({ title: 'Error', description: err.response?.data?.detail || err.message, type: 'error' });
        }
    };

    const handleApprove = async (proposalId) => {
        try {
            const res = await axios.post(`/boardrooms/proposals/${proposalId}/approve`);
            toast({ title: 'Share Yielded', description: res.data.message, type: 'success' });
            fetchData();
        } catch (err) {
            toast({ title: 'Error', description: err.response?.data?.detail || err.message, type: 'error' });
        }
    };

    const handleUnlock = async (proposalId) => {
        try {
            const res = await axios.get(`/boardrooms/proposals/${proposalId}/unlock`);
            setUnlockedDoc(res.data);
        } catch (err) {
            toast({ title: 'Decryption Failed', description: err.response?.data?.detail || err.message, type: 'error' });
        }
    };

    const formatTimeRemaining = (seconds) => {
        if (seconds == null || seconds <= 0) return 'Expired';
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        if (h > 0) return `${h}h ${m}m remaining`;
        if (m > 0) return `${m}m ${s}s remaining`;
        return `${s}s remaining`;
    };

    if (isLoading) {
        return <div className="h-full flex items-center justify-center"><div className="h-8 w-8 rounded-full border-2 border-emerald-500/20 border-t-emerald-500 animate-spin" /></div>;
    }

    if (!boardroom) return null;

    return (
        <div className="h-full flex flex-col space-y-6 lg:space-y-8">
            <div className="flex items-center justify-between shrink-0 mb-2">
                <div className="flex items-center gap-4">
                    <button onClick={() => navigate('/boardroom')} className="p-2 hover:bg-white/5 rounded-full transition-colors">
                        <ArrowLeft className="h-5 w-5 text-gray-400" />
                    </button>
                    <div>
                        <div className="flex items-center gap-2">
                            <h1 className="text-2xl font-display font-bold text-white tracking-tight">{boardroom.name}</h1>
                            <div className="bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-[10px] px-2 py-0.5 rounded font-mono uppercase tracking-widest hidden md:flex items-center gap-1">
                                <Shield className="h-3 w-3" /> Secure Vault
                            </div>
                        </div>
                        <p className="text-gray-500 text-sm mt-0.5 font-mono">
                            Threshold: {boardroom.threshold_m} of {boardroom.total_members} approvals required
                        </p>
                    </div>
                </div>
                <Button onClick={() => setIsProposing(!isProposing)} variant="neon" className="bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border-emerald-500/30 px-6">
                    {isProposing ? 'Cancel' : <><Upload className="h-4 w-4 mr-2" /> Propose Execution</>}
                </Button>
            </div>

            <AnimatePresence>
                {isProposing && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden"
                    >
                        <Card className="bg-[#050505] border-white/[0.06] mb-6 shadow-2xl relative">
                            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-emerald-500/40 to-transparent" />
                            <CardContent className="p-6">
                                <form onSubmit={handlePropose} className="space-y-4">
                                    <div>
                                        <label className="text-xs font-medium text-gray-400 mb-1 block">Proposal Title</label>
                                        <input
                                            type="text"
                                            value={newTitle}
                                            onChange={(e) => setNewTitle(e.target.value)}
                                            className="w-full bg-black border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500/50"
                                            required
                                            placeholder="e.g. Q4 Merger Authorization"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-gray-400 mb-1 block">Execution Document (Plaintext)</label>
                                        <textarea
                                            value={newContent}
                                            onChange={(e) => setNewContent(e.target.value)}
                                            className="w-full min-h-[160px] bg-black border border-white/10 rounded-lg px-3 py-3 text-sm text-gray-300 focus:outline-none focus:border-emerald-500/50 font-mono resize-none"
                                            required
                                            placeholder="Enter the highly confidential text here. It will be mathematically dismantled into shares upon submission."
                                        />
                                    </div>

                                    {/* Auto-Destruct Timer */}
                                    <div className={`border rounded-lg p-4 transition-colors ${enableTimelock ? 'border-amber-500/30 bg-amber-500/[0.03]' : 'border-white/[0.06] bg-black/40'}`}>
                                        <div className="flex items-center justify-between">
                                            <div className="flex items-center gap-2.5">
                                                <div className={`p-1.5 rounded-md transition-colors ${enableTimelock ? 'bg-amber-500/15' : 'bg-white/5'}`}>
                                                    <Clock className={`h-3.5 w-3.5 transition-colors ${enableTimelock ? 'text-amber-400' : 'text-gray-500'}`} />
                                                </div>
                                                <div>
                                                    <span className={`text-xs font-medium transition-colors ${enableTimelock ? 'text-amber-300' : 'text-gray-400'}`}>Auto-Destruct</span>
                                                    {enableTimelock && (
                                                        <span className="text-[10px] text-amber-500/60 font-mono ml-2">
                                                            {tlHours > 0 && `${tlHours}h `}{tlMins > 0 && `${tlMins}m `}{tlSecs > 0 && `${tlSecs}s`}
                                                            {tlHours === 0 && tlMins === 0 && tlSecs === 0 && 'not set'}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={() => setEnableTimelock(!enableTimelock)}
                                                className={`relative w-11 h-6 rounded-full transition-all duration-200 ${enableTimelock ? 'bg-amber-500/50 shadow-[0_0_12px_rgba(245,158,11,0.15)]' : 'bg-white/10'}`}
                                            >
                                                <div className={`absolute top-1 w-4 h-4 rounded-full transition-all duration-200 ${enableTimelock ? 'translate-x-6 bg-amber-300 shadow-sm' : 'translate-x-1 bg-gray-500'}`} />
                                            </button>
                                        </div>
                                        <AnimatePresence>
                                            {enableTimelock && (
                                                <motion.div
                                                    initial={{ opacity: 0, height: 0 }}
                                                    animate={{ opacity: 1, height: 'auto' }}
                                                    exit={{ opacity: 0, height: 0 }}
                                                    transition={{ duration: 0.2 }}
                                                    className="overflow-hidden"
                                                >
                                                    <div className="mt-4 space-y-3">
                                                        {/* Preset buttons */}
                                                        <div className="flex flex-wrap gap-1.5">
                                                            {[
                                                                { label: '5m', h: 0, m: 5, s: 0 },
                                                                { label: '15m', h: 0, m: 15, s: 0 },
                                                                { label: '30m', h: 0, m: 30, s: 0 },
                                                                { label: '1h', h: 1, m: 0, s: 0 },
                                                                { label: '6h', h: 6, m: 0, s: 0 },
                                                                { label: '24h', h: 24, m: 0, s: 0 },
                                                                { label: '72h', h: 72, m: 0, s: 0 },
                                                            ].map((p) => (
                                                                <button
                                                                    key={p.label}
                                                                    type="button"
                                                                    onClick={() => { setTlHours(p.h); setTlMins(p.m); setTlSecs(p.s); setTlPreset(p.label); }}
                                                                    className={`px-3 py-1 rounded text-[11px] font-mono font-medium transition-all
                                                                        ${tlPreset === p.label
                                                                            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-[0_0_8px_rgba(245,158,11,0.1)]'
                                                                            : 'bg-white/[0.04] text-gray-500 border border-white/[0.06] hover:bg-white/[0.08] hover:text-gray-300'
                                                                        }`}
                                                                >
                                                                    {p.label}
                                                                </button>
                                                            ))}
                                                        </div>

                                                        {/* Custom H:M:S input */}
                                                        <div className="flex items-center gap-1">
                                                            <div className="flex items-center bg-black/60 border border-white/[0.08] rounded-lg overflow-hidden">
                                                                <div className="flex flex-col items-center px-2.5 py-1.5">
                                                                    <span className="text-[8px] uppercase tracking-widest text-gray-600 mb-0.5">hrs</span>
                                                                    <input
                                                                        type="number"
                                                                        min="0"
                                                                        max="168"
                                                                        value={tlHours}
                                                                        onChange={(e) => { setTlHours(Math.max(0, parseInt(e.target.value) || 0)); setTlPreset(null); }}
                                                                        className="w-10 bg-transparent text-center text-sm text-amber-400 font-mono focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                                                                    />
                                                                </div>
                                                                <span className="text-amber-500/40 text-sm font-mono">:</span>
                                                                <div className="flex flex-col items-center px-2.5 py-1.5">
                                                                    <span className="text-[8px] uppercase tracking-widest text-gray-600 mb-0.5">min</span>
                                                                    <input
                                                                        type="number"
                                                                        min="0"
                                                                        max="59"
                                                                        value={tlMins}
                                                                        onChange={(e) => { setTlMins(Math.min(59, Math.max(0, parseInt(e.target.value) || 0))); setTlPreset(null); }}
                                                                        className="w-10 bg-transparent text-center text-sm text-amber-400 font-mono focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                                                                    />
                                                                </div>
                                                                <span className="text-amber-500/40 text-sm font-mono">:</span>
                                                                <div className="flex flex-col items-center px-2.5 py-1.5">
                                                                    <span className="text-[8px] uppercase tracking-widest text-gray-600 mb-0.5">sec</span>
                                                                    <input
                                                                        type="number"
                                                                        min="0"
                                                                        max="59"
                                                                        value={tlSecs}
                                                                        onChange={(e) => { setTlSecs(Math.min(59, Math.max(0, parseInt(e.target.value) || 0))); setTlPreset(null); }}
                                                                        className="w-10 bg-transparent text-center text-sm text-amber-400 font-mono focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                                                                    />
                                                                </div>
                                                            </div>
                                                            <span className="text-[10px] text-gray-600 ml-2">until self-destruct</span>
                                                        </div>

                                                        <p className="text-[10px] text-amber-500/40 font-mono leading-relaxed">
                                                            Encryption key destroyed on expiry. Document becomes permanently unrecoverable.
                                                        </p>
                                                    </div>
                                                </motion.div>
                                            )}
                                        </AnimatePresence>
                                    </div>

                                    <div className="flex justify-end pt-2">
                                        <Button type="submit" variant="neon" className="bg-emerald-500/10 text-emerald-400 border-emerald-500/30">
                                            Split & Distribute Shares
                                        </Button>
                                    </div>
                                </form>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="space-y-4">
                {proposals.length === 0 ? (
                    <div className="py-20 text-center text-gray-500 text-sm bg-[#050505] border border-white/[0.04] rounded-xl border-dashed">
                        No proposals have been initiated in this boardroom.
                    </div>
                ) : (
                    (proposals || []).map((p) => {
                        const isExecuted = p.status === 'executed';
                        const progress = Math.min(100, (p.approvals / boardroom.threshold_m) * 100);
                        const hasTimelock = p.has_timelock;
                        const timelockExpired = p.timelock_expired;

                        return (
                            <Card key={p.id} className={`bg-[#050505] border-white/[0.06] overflow-hidden relative ${isExecuted ? 'border-emerald-500/20' : ''} ${timelockExpired ? 'border-red-500/20' : ''}`}>
                                {isExecuted && !timelockExpired && <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-500/10 blur-3xl pointer-events-none rounded-full translate-x-1/2 -translate-y-1/2" />}
                                {timelockExpired && <div className="absolute top-0 right-0 w-32 h-32 bg-red-500/10 blur-3xl pointer-events-none rounded-full translate-x-1/2 -translate-y-1/2" />}
                                <CardContent className="p-5 flex flex-col md:flex-row md:items-center justify-between gap-6">
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-3 mb-2">
                                            {timelockExpired ? (
                                                <AlertTriangle className="h-5 w-5 text-red-500/80 shrink-0" />
                                            ) : isExecuted ? (
                                                <Unlock className="h-5 w-5 text-emerald-500 shrink-0" />
                                            ) : (
                                                <Lock className="h-5 w-5 text-red-500/80 shrink-0" />
                                            )}
                                            <h3 className="text-lg font-semibold text-white truncate w-full pr-4">{p.title}</h3>
                                        </div>
                                        <div className="text-xs text-gray-500 font-mono mb-4 flex items-center gap-4 flex-wrap">
                                            <span>Initiator: <span className="text-gray-300">{p.initiator_username}</span></span>
                                            <span>ID: {p.id.substring(0, 8)}</span>
                                            {hasTimelock && (
                                                <span className={`flex items-center gap-1 ${timelockExpired ? 'text-red-400' : 'text-amber-400'}`}>
                                                    <Clock className="h-3 w-3" />
                                                    {timelockExpired ? 'EXPIRED' : (
                                                        p.expires_at ? new Date(p.expires_at).toLocaleString() : 'Timed'
                                                    )}
                                                </span>
                                            )}
                                        </div>

                                        {/* Progress Bar */}
                                        <div className="max-w-md">
                                            <div className="flex items-center justify-between text-[10px] text-gray-400 font-mono mb-1 uppercase tracking-wider">
                                                <span>Approvals</span>
                                                <span className={isExecuted ? 'text-emerald-400' : 'text-gray-400'}>{p.approvals} / {boardroom.threshold_m}</span>
                                            </div>
                                            <div className="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
                                                <div
                                                    className={`h-full rounded-full transition-all duration-1000 ${timelockExpired ? 'bg-red-500/50' : isExecuted ? 'bg-emerald-500' : 'bg-red-500/50'}`}
                                                    style={{ width: `${progress}%` }}
                                                />
                                            </div>
                                        </div>
                                    </div>

                                    <div className="flex md:flex-col items-center justify-end gap-3 shrink-0">
                                        {timelockExpired ? (
                                            <div className="bg-red-500/10 text-red-400 px-3 py-1 text-xs rounded font-mono font-bold border border-red-500/20 flex items-center gap-2">
                                                <AlertTriangle className="h-3 w-3" /> SELF-DESTRUCTED
                                            </div>
                                        ) : isExecuted ? (
                                            <div className="flex flex-col items-end gap-3">
                                                <div className="bg-emerald-500/10 text-emerald-400 px-3 py-1 text-xs rounded font-mono font-bold border border-emerald-500/20 flex items-center gap-2">
                                                    <CheckCircle2 className="h-3 w-3" /> THRESHOLD MET
                                                </div>
                                                <Button onClick={() => handleUnlock(p.id)} variant="outline" size="sm" className="border-emerald-500/30 text-emerald-400 hover:bg-emerald-500/10 w-full">
                                                    <FileText className="h-3.5 w-3.5 mr-2" /> Read Plaintext
                                                </Button>
                                            </div>
                                        ) : (
                                            <div className="flex flex-col items-end gap-3">
                                                {p.user_has_approved ? (
                                                    <div className="text-xs text-emerald-500 font-mono flex items-center gap-1.5 border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 rounded">
                                                        <CheckCircle2 className="h-3.5 w-3.5" /> Share Yielded
                                                    </div>
                                                ) : (
                                                    <Button onClick={() => handleApprove(p.id)} variant="neon" size="sm" className="w-full">
                                                        Yield Share
                                                    </Button>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                </CardContent>
                            </Card>
                        )
                    })
                )}
            </div>

            {/* Read Document Modal */}
            <AnimatePresence>
                {unlockedDoc && (
                    <motion.div
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
                        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
                        onClick={() => setUnlockedDoc(null)}
                    >
                        <motion.div
                            initial={{ scale: 0.95, y: 20 }} animate={{ scale: 1, y: 0 }} exit={{ scale: 0.95, y: 20 }}
                            onClick={(e) => e.stopPropagation()}
                            className="bg-[#0a0a0a] border border-white/10 rounded-xl shadow-2xl w-full max-w-3xl overflow-hidden flex flex-col max-h-[85vh]"
                        >
                            <div className="p-4 border-b border-white/[0.04] flex items-center justify-between bg-[#050505]">
                                <div className="flex items-center gap-3">
                                    <Unlock className="h-5 w-5 text-emerald-500" />
                                    <h3 className="font-display font-semibold text-white">Execution Document Decrypted</h3>
                                </div>
                                <div className="flex items-center gap-3">
                                    {unlockedDoc.watermarked && (
                                        <div className="flex items-center gap-1.5 text-[10px] text-cyan-400 font-mono border border-cyan-500/20 bg-cyan-500/5 px-2 py-1 rounded">
                                            <Fingerprint className="h-3 w-3" /> WATERMARKED COPY
                                        </div>
                                    )}
                                    {unlockedDoc.timelock_remaining_seconds != null && (
                                        <div className="flex items-center gap-1.5 text-[10px] text-amber-400 font-mono border border-amber-500/20 bg-amber-500/5 px-2 py-1 rounded">
                                            <Clock className="h-3 w-3" /> {formatTimeRemaining(unlockedDoc.timelock_remaining_seconds)}
                                        </div>
                                    )}
                                    <button onClick={() => setUnlockedDoc(null)} className="text-gray-500 hover:text-white transition-colors text-sm font-mono">
                                        [CLOSE]
                                    </button>
                                </div>
                            </div>
                            <div className="p-6 overflow-y-auto w-full font-mono text-sm text-gray-300 leading-relaxed bg-[#020202] flex-1 whitespace-pre-wrap">
                                {/* Simulated Document Header */}
                                <div className="border-b border-white/10 pb-4 mb-4 select-none opacity-50 text-xs">
                                    <div>CLASSIFICATION: TOP SECRET // BOARDROOM ONLY</div>
                                    <div>TITLE: {unlockedDoc.title}</div>
                                    <div>CRYPTOGRAPHIC INTEGRITY: VERIFIED</div>
                                    {unlockedDoc.watermarked && <div>LEAK ATTRIBUTION: STEGANOGRAPHIC WATERMARK EMBEDDED</div>}
                                </div>
                                {unlockedDoc.content}
                            </div>
                        </motion.div>
                    </motion.div>
                )}
            </AnimatePresence>

        </div>
    );
}
