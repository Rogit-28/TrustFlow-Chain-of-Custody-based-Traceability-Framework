import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { useToast } from '../components/ui/toast';
import { Users, FileText, Upload, CheckCircle2, Lock, Unlock, ArrowLeft, Shield, Clock, AlertTriangle, Fingerprint, Activity } from 'lucide-react';
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

    const [unlockedDoc, setUnlockedDoc] = useState(null);

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
        return <div className="h-full flex items-center justify-center"><Activity className="h-6 w-6 text-gray-600 animate-spin" /></div>;
    }

    if (!boardroom) return null;

    return (
        <div className="h-full flex flex-col space-y-6 lg:space-y-8">
            {/* Header */}
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 shrink-0 pb-6 border-b border-white/[0.04]">
                <div className="flex items-center gap-3">
                    <button onClick={() => navigate('/boardroom')} className="p-2 bg-white/[0.03] hover:bg-white/[0.06] border border-white/[0.06] hover:border-white/[0.1] rounded-lg transition-all group">
                        <ArrowLeft className="h-4 w-4 text-gray-500 group-hover:text-white group-hover:-translate-x-0.5 transition-all" />
                    </button>
                    <div>
                        <h1 className="text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
                            {boardroom.name}
                        </h1>
                        <div className="flex items-center gap-3 mt-1">
                            <p className="text-gray-600 text-sm">
                                Threshold <span className="text-white font-medium">{boardroom.threshold_m}</span> / <span className="text-gray-400">{boardroom.total_members}</span> required
                            </p>
                            <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border text-emerald-400/80 border-emerald-500/20 bg-emerald-500/5">E2E Secure</span>
                        </div>
                    </div>
                </div>
                <Button onClick={() => setIsProposing(!isProposing)} variant="neon" className="gap-2 w-full md:w-auto">
                    {isProposing ? 'Cancel' : <><Upload className="h-4 w-4" /> Propose Execution</>}
                </Button>
            </div>

            {/* Propose Form */}
            <AnimatePresence>
                {isProposing && (
                    <motion.div
                        initial={{ opacity: 0, height: 0, y: -20 }}
                        animate={{ opacity: 1, height: 'auto', y: 0 }}
                        exit={{ opacity: 0, height: 0, y: -20 }}
                        transition={{ duration: 0.3, ease: "easeOut" }}
                        className="overflow-visible"
                    >
                        <Card className="bg-[#050505] border-white/[0.06] mb-6 shadow-2xl relative">
                            <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-red-500/30 to-transparent" />

                            <CardHeader className="pb-4 border-b border-white/[0.04]">
                                <CardTitle className="text-base flex items-center gap-2">
                                    <Shield className="h-4 w-4 text-red-500" /> Initiate Secure Proposal
                                </CardTitle>
                                <CardDescription>Content will be cryptographically split via Shamir's scheme.</CardDescription>
                            </CardHeader>
                            <CardContent className="pt-6">
                                <form onSubmit={handlePropose} className="space-y-5">
                                    <div className="space-y-1.5">
                                        <label className="text-xs text-gray-400 block">Proposal Title</label>
                                        <input
                                            type="text"
                                            value={newTitle}
                                            onChange={(e) => setNewTitle(e.target.value)}
                                            className="w-full bg-[#0a0a0a] border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-white focus:outline-none focus:border-red-500/40 focus:ring-1 focus:ring-red-500/30 shadow-inner transition-colors placeholder:text-gray-700"
                                            required
                                            placeholder="e.g. Q4 Merger Authorization"
                                        />
                                    </div>
                                    <div className="space-y-1.5">
                                        <label className="text-xs text-gray-400 block">Execution Document</label>
                                        <textarea
                                            value={newContent}
                                            onChange={(e) => setNewContent(e.target.value)}
                                            className="w-full min-h-[160px] bg-[#0a0a0a] border border-white/[0.08] border-l-2 border-l-red-500/20 rounded-lg px-4 py-3 text-sm text-gray-300 placeholder:text-gray-700 focus:outline-none focus:border-red-500/40 focus:ring-1 focus:ring-red-500/30 font-mono resize-y shadow-inner leading-relaxed transition-colors"
                                            required
                                            placeholder="Enter confidential text here...&#10;Document will be split into shares upon submission."
                                            spellCheck="false"
                                        />
                                    </div>

                                    {/* Auto-Destruct Timer */}
                                    <div className={`border rounded-xl transition-all duration-300 ${enableTimelock ? 'border-red-500/20 bg-red-500/[0.03]' : 'border-white/[0.06] bg-white/[0.02] hover:border-white/[0.1]'}`}>
                                        <div className="p-4 flex items-center justify-between cursor-pointer" onClick={() => setEnableTimelock(!enableTimelock)}>
                                            <div className="flex items-center gap-3">
                                                <div className={`p-2 rounded-lg transition-all ${enableTimelock ? 'bg-red-500/10 border border-red-500/30 shadow-[0_0_8px_rgba(255,7,58,0.15)]' : 'bg-white/[0.04]'}`}>
                                                    <Clock className={`h-4 w-4 transition-colors ${enableTimelock ? 'text-red-500' : 'text-gray-500'}`} />
                                                </div>
                                                <div>
                                                    <h4 className={`text-sm font-medium transition-colors ${enableTimelock ? 'text-white' : 'text-gray-400'}`}>Auto-Destruct Timer</h4>
                                                    <p className="text-[10px] text-gray-500 mt-0.5">Time-lock encryption with automatic key destruction.</p>
                                                </div>
                                            </div>
                                            <button
                                                type="button"
                                                onClick={(e) => { e.stopPropagation(); setEnableTimelock(!enableTimelock); }}
                                                className={`relative w-11 h-6 rounded-full transition-all duration-300 outline-none shrink-0 ${enableTimelock ? 'bg-red-500/50 shadow-[0_0_12px_rgba(255,7,58,0.3)]' : 'bg-white/10'}`}
                                            >
                                                <div className={`absolute top-1 w-4 h-4 rounded-full transition-all duration-300 shadow-sm ${enableTimelock ? 'translate-x-6 bg-red-400' : 'translate-x-1 bg-gray-400'}`} />
                                            </button>
                                        </div>
                                        <AnimatePresence>
                                            {enableTimelock && (
                                                <motion.div
                                                    initial={{ opacity: 0, height: 0 }}
                                                    animate={{ opacity: 1, height: 'auto' }}
                                                    exit={{ opacity: 0, height: 0 }}
                                                    transition={{ duration: 0.3, ease: 'easeOut' }}
                                                    className="border-t border-white/[0.04]"
                                                >
                                                    <div className="p-4 pt-4 space-y-4">
                                                        {/* Presets */}
                                                        <div>
                                                            <div className="text-[10px] uppercase tracking-wider text-gray-400 font-medium mb-2">Duration</div>
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
                                                                        className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-all
                                                                            ${tlPreset === p.label
                                                                                ? 'bg-red-500/15 text-red-400 border border-red-500/30 shadow-[0_0_6px_rgba(255,7,58,0.15)]'
                                                                                : 'bg-white/[0.04] text-gray-400 border border-white/[0.08] hover:bg-white/[0.08] hover:text-white'
                                                                            }`}
                                                                    >
                                                                        {p.label}
                                                                    </button>
                                                                ))}
                                                            </div>
                                                        </div>

                                                        {/* Custom H:M:S */}
                                                        <div>
                                                            <div className="text-[10px] uppercase tracking-wider text-gray-400 font-medium mb-2">Custom</div>
                                                            <div className="flex items-center bg-[#050505] border border-white/[0.1] rounded-lg overflow-hidden w-max shadow-lg">
                                                                <div className="flex flex-col items-center px-3 py-2 border-r border-white/[0.08]">
                                                                    <span className="text-[9px] uppercase tracking-wider text-gray-500 mb-1">hrs</span>
                                                                    <input
                                                                        type="number"
                                                                        min="0"
                                                                        max="168"
                                                                        value={tlHours}
                                                                        onChange={(e) => { setTlHours(Math.max(0, parseInt(e.target.value) || 0)); setTlPreset(null); }}
                                                                        className="w-10 bg-transparent text-center text-lg text-red-400 font-mono focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                                                                    />
                                                                </div>
                                                                <div className="flex flex-col items-center px-3 py-2 border-r border-white/[0.08]">
                                                                    <span className="text-[9px] uppercase tracking-wider text-gray-500 mb-1">min</span>
                                                                    <input
                                                                        type="number"
                                                                        min="0"
                                                                        max="59"
                                                                        value={tlMins}
                                                                        onChange={(e) => { setTlMins(Math.min(59, Math.max(0, parseInt(e.target.value) || 0))); setTlPreset(null); }}
                                                                        className="w-10 bg-transparent text-center text-lg text-red-400 font-mono focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                                                                    />
                                                                </div>
                                                                <div className="flex flex-col items-center px-3 py-2">
                                                                    <span className="text-[9px] uppercase tracking-wider text-gray-500 mb-1">sec</span>
                                                                    <input
                                                                        type="number"
                                                                        min="0"
                                                                        max="59"
                                                                        value={tlSecs}
                                                                        onChange={(e) => { setTlSecs(Math.min(59, Math.max(0, parseInt(e.target.value) || 0))); setTlPreset(null); }}
                                                                        className="w-10 bg-transparent text-center text-lg text-red-400 font-mono focus:outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
                                                                    />
                                                                </div>
                                                            </div>
                                                        </div>

                                                        <div className="flex items-start gap-2 bg-red-500/[0.07] border border-red-500/20 rounded-lg p-3">
                                                            <AlertTriangle className="h-3.5 w-3.5 text-red-500/80 shrink-0 mt-0.5" />
                                                            <p className="text-[11px] text-gray-400 leading-relaxed">
                                                                Encryption key is destroyed on expiry. Document becomes permanently unrecoverable.
                                                            </p>
                                                        </div>
                                                    </div>
                                                </motion.div>
                                            )}
                                        </AnimatePresence>
                                    </div>

                                    <div className="flex justify-end pt-2">
                                        <Button type="submit" variant="neon" className="px-6">
                                            Split & Distribute Shares
                                        </Button>
                                    </div>
                                </form>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Proposals */}
            <div className="space-y-3 pb-8">
                {proposals.length === 0 ? (
                    <div className="flex flex-col items-center justify-center p-16 border border-white/[0.04] bg-white/[0.01] rounded-xl border-dashed">
                        <FileText className="h-10 w-10 text-gray-700 mb-3" />
                        <p className="text-gray-600 text-sm">No active proposals.</p>
                    </div>
                ) : (
                    (proposals || []).map((p, index) => {
                        const isExecuted = p.status === 'executed';
                        const hasTimelock = p.has_timelock;
                        const timelockExpired = p.timelock_expired;

                        return (
                            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04 }} key={p.id}>
                                <Card className={`bg-[#050505] relative transition-all duration-300 overflow-hidden
                                    ${timelockExpired ? 'border-white/[0.06] border-l-2 border-l-red-500/40 bg-red-500/[0.02] opacity-70' : ''}
                                    ${isExecuted && !timelockExpired ? 'border-white/[0.06] border-l-2 border-l-emerald-500/30 bg-emerald-500/[0.02]' : ''}
                                    ${!isExecuted && !timelockExpired ? 'border-white/[0.06] border-l-2 border-l-white/[0.1] hover:border-white/[0.12]' : ''}
                                `}>
                                    <div className={`absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent to-transparent
                                        ${timelockExpired ? 'via-red-500/30' : isExecuted ? 'via-emerald-500/30' : 'via-white/[0.06]'}
                                    `} />

                                    <CardContent className="p-5 md:p-6 flex flex-col xl:flex-row xl:items-center justify-between gap-5">
                                        <div className="flex-1 min-w-0">
                                            <div className="flex items-center gap-3 mb-3">
                                                {timelockExpired ? (
                                                    <AlertTriangle className="h-5 w-5 text-red-500 shrink-0" />
                                                ) : isExecuted ? (
                                                    <Unlock className="h-5 w-5 text-emerald-400 shrink-0" />
                                                ) : (
                                                    <Lock className="h-5 w-5 text-gray-500 shrink-0" />
                                                )}
                                                <h3 className="text-base font-display font-semibold text-white truncate">{p.title}</h3>
                                            </div>

                                            <div className="flex items-center gap-3 text-[10px] text-gray-600 font-mono mb-4 flex-wrap">
                                                <span>by <span className="text-gray-400">{p.initiator_username}</span></span>
                                                <span className="opacity-30">|</span>
                                                <span>{p.id.substring(0, 8)}</span>
                                                {hasTimelock && (
                                                    <>
                                                        <span className="opacity-30">|</span>
                                                        <span className={`flex items-center gap-1 ${timelockExpired ? 'text-red-400' : 'text-gray-400'}`}>
                                                            <Clock className="h-3 w-3" />
                                                            {timelockExpired ? 'Expired' : (
                                                                p.expires_at ? new Date(p.expires_at).toLocaleString() : 'Timed'
                                                            )}
                                                        </span>
                                                    </>
                                                )}
                                            </div>

                                            {/* Progress */}
                                            <div className="max-w-md">
                                                <div className="flex items-center justify-between text-[10px] text-gray-600 mb-1.5">
                                                    <span>Approvals</span>
                                                    <span>
                                                        <span className="text-white">{p.approvals}</span> / {boardroom.threshold_m}
                                                    </span>
                                                </div>
                                                <div className="h-2 w-full bg-white/[0.06] rounded-full overflow-hidden flex shadow-[inset_0_1px_3px_rgba(0,0,0,0.4)]">
                                                    {[...Array(boardroom.threshold_m)].map((_, i) => (
                                                        <div key={i} className={`h-full flex-1 border-r border-[#050505] last:border-0 transition-all duration-500
                                                            ${i < p.approvals
                                                                ? timelockExpired ? 'bg-red-500' : 'bg-emerald-500'
                                                                : 'bg-white/[0.08]'
                                                            }
                                                        `} />
                                                    ))}
                                                </div>
                                            </div>
                                        </div>

                                        <div className="flex xl:flex-col items-center justify-end gap-2 shrink-0 pt-3 xl:pt-0 border-t border-white/[0.04] xl:border-0">
                                            {timelockExpired ? (
                                                <span className="text-[9px] uppercase font-bold tracking-wider px-2 py-1 rounded border text-red-400/80 border-red-500/20 bg-red-500/5 flex items-center gap-1.5">
                                                    <AlertTriangle className="h-3 w-3" /> Self-Destructed
                                                </span>
                                            ) : isExecuted ? (
                                                <div className="flex flex-col items-end gap-2 w-full xl:w-auto">
                                                    <span className="text-[9px] uppercase font-bold tracking-wider px-2 py-1 rounded border text-emerald-400/80 border-emerald-500/20 bg-emerald-500/5 flex items-center gap-1.5">
                                                        <CheckCircle2 className="h-3 w-3" /> Threshold Met
                                                    </span>
                                                    <Button onClick={() => handleUnlock(p.id)} variant="secondary" size="sm" className="gap-1.5 w-full xl:w-auto">
                                                        <FileText className="h-3.5 w-3.5" /> Read Plaintext
                                                    </Button>
                                                </div>
                                            ) : (
                                                <div className="w-full xl:w-auto">
                                                    {p.user_has_approved ? (
                                                        <span className="text-[9px] uppercase font-bold tracking-wider px-2 py-1 rounded border text-emerald-400/80 border-emerald-500/20 bg-emerald-500/5 flex items-center gap-1.5">
                                                            <CheckCircle2 className="h-3 w-3" /> Share Yielded
                                                        </span>
                                                    ) : (
                                                        <Button onClick={() => handleApprove(p.id)} variant="neon" size="sm" className="w-full xl:w-auto px-5">
                                                            Yield Share
                                                        </Button>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        )
                    })
                )}
            </div>

            {/* Read Document Modal */}
            <AnimatePresence>
                {unlockedDoc && (
                    <>
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 bg-black/70 z-50" onClick={() => setUnlockedDoc(null)} />
                        <motion.div initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.96 }} className="fixed inset-0 m-auto w-full max-w-3xl h-fit max-h-[85vh] z-50 p-4">
                            <Card className="bg-[#050505] border-white/[0.06] flex flex-col max-h-[85vh] relative">
                                <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-red-500/30 to-transparent" />
                                <div className="p-5 border-b border-white/[0.04] flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0">
                                    <div className="flex items-center gap-2">
                                        <Unlock className="h-4 w-4 text-red-500" />
                                        <h3 className="font-display font-semibold text-white text-lg">Decrypted Document</h3>
                                    </div>
                                    <div className="flex flex-wrap items-center gap-2">
                                        {unlockedDoc.watermarked && (
                                            <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border text-cyan-400/80 border-cyan-500/20 bg-cyan-500/5 flex items-center gap-1">
                                                <Fingerprint className="h-3 w-3" /> Watermarked
                                            </span>
                                        )}
                                        {unlockedDoc.timelock_remaining_seconds != null && (
                                            <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border text-red-400/80 border-red-500/20 bg-red-500/5 flex items-center gap-1">
                                                <Clock className="h-3 w-3" /> {formatTimeRemaining(unlockedDoc.timelock_remaining_seconds)}
                                            </span>
                                        )}
                                        <Button variant="ghost" size="sm" onClick={() => setUnlockedDoc(null)}>Close</Button>
                                    </div>
                                </div>
                                <div className="overflow-y-auto flex-1">
                                    <div className="m-5 mb-0 p-4 bg-[#0a0a0a] border border-white/[0.06] rounded-lg text-xs text-gray-500 space-y-2.5">
                                        <div className="flex items-center justify-between">
                                            <span>Subject</span>
                                            <span className="text-white font-medium">{unlockedDoc.title}</span>
                                        </div>
                                        <div className="flex items-center justify-between">
                                            <span>Crypto Status</span>
                                            <span className="text-emerald-400 flex items-center gap-1"><CheckCircle2 className="h-3 w-3" /> Verified</span>
                                        </div>
                                        {unlockedDoc.watermarked && (
                                            <div className="flex items-center justify-between">
                                                <span>Attribution</span>
                                                <span className="text-cyan-400 flex items-center gap-1"><Fingerprint className="h-3 w-3" /> Tracer Active</span>
                                            </div>
                                        )}
                                    </div>
                                    <div className="mx-5 my-5 p-6 font-mono text-sm text-gray-300 leading-relaxed whitespace-pre-wrap selection:bg-red-500/20 selection:text-white bg-black/40 border-l-2 border-l-white/[0.06] rounded-r-lg">
                                        {unlockedDoc.content}
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
