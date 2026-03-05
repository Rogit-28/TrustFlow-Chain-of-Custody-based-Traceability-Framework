import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { useToast } from '../components/ui/toast';
import { Users, Plus, ShieldCheck, ChevronRight, Activity } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import axios from 'axios';

export default function BoardroomView() {
    const [boardrooms, setBoardrooms] = useState([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isCreating, setIsCreating] = useState(false);

    const [newName, setNewName] = useState('');
    const [newMembers, setNewMembers] = useState('');
    const [newThreshold, setNewThreshold] = useState(2);
    const toast = useToast();
    const navigate = useNavigate();

    useEffect(() => {
        fetchBoardrooms();
    }, []);

    const fetchBoardrooms = async () => {
        try {
            const res = await axios.get('/boardrooms');
            setBoardrooms(res.data.boardrooms || []);
        } catch (err) {
            toast({ title: 'Failed to load boardrooms', description: err.message, type: 'error' });
        } finally {
            setIsLoading(false);
        }
    };

    const handleCreate = async (e) => {
        e.preventDefault();
        try {
            const membersList = newMembers.split(',').map(s => s.trim()).filter(Boolean);
            if (membersList.length === 0) {
                toast({ title: 'Error', description: 'Add at least one other member', type: 'error' });
                return;
            }

            await axios.post('/boardrooms', {
                name: newName,
                threshold_m: parseInt(newThreshold, 10),
                member_usernames: membersList
            });

            toast({ title: 'Success', description: 'Boardroom created securely.', type: 'success' });
            setIsCreating(false);
            setNewName('');
            setNewMembers('');
            setNewThreshold(2);
            fetchBoardrooms();

        } catch (err) {
            toast({
                title: 'Creation failed',
                description: err.response?.data?.detail || err.message,
                type: 'error'
            });
        }
    };

    return (
        <div className="h-full flex flex-col space-y-6 lg:space-y-8">
            {/* Header */}
            <div className="flex items-center justify-between shrink-0">
                <div>
                    <h1 className="text-2xl font-display font-bold text-white tracking-tight flex items-center gap-2">
                        <Users className="h-6 w-6 text-gray-500" /> Inner Circle
                    </h1>
                    <p className="text-gray-600 text-sm mt-0.5">Threshold-secured boardrooms with Shamir's Secret Sharing.</p>
                </div>
                <Button onClick={() => setIsCreating(!isCreating)} variant="neon" className="gap-2">
                    {isCreating ? 'Cancel' : <><Plus className="h-4 w-4" /> New Boardroom</>}
                </Button>
            </div>

            {/* Create Form */}
            <AnimatePresence>
                {isCreating && (
                    <motion.div
                        initial={{ opacity: 0, height: 0, y: -20 }}
                        animate={{ opacity: 1, height: 'auto', y: 0 }}
                        exit={{ opacity: 0, height: 0, y: -20 }}
                        transition={{ duration: 0.3, ease: "easeOut" }}
                        className="overflow-hidden"
                    >
                        <Card className="bg-[#050505] border-white/[0.06] relative">
                            <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-red-500/30 to-transparent" />

                            <CardHeader className="pb-4 border-b border-white/[0.04]">
                                <CardTitle className="text-base flex items-center gap-2">
                                    <ShieldCheck className="h-4 w-4 text-red-500" /> Initialize Secure Vault
                                </CardTitle>
                                <CardDescription>
                                    Execution documents will be cryptographically split. M-of-N threshold required for reconstruction.
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="pt-6">
                                <form onSubmit={handleCreate} className="space-y-5">
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                                        <div className="space-y-1.5">
                                            <label className="text-xs text-gray-400 block">Vault Name</label>
                                            <input
                                                type="text"
                                                value={newName}
                                                onChange={(e) => setNewName(e.target.value)}
                                                className="w-full bg-[#0a0a0a] border border-white/[0.08] rounded-lg px-4 py-2.5 text-sm text-white focus:outline-none focus:border-red-500/40 focus:ring-1 focus:ring-red-500/30 shadow-inner transition-colors placeholder:text-gray-700"
                                                required
                                                placeholder="e.g. Project Orion Executives"
                                            />
                                        </div>
                                        <div className="space-y-1.5">
                                            <label className="text-xs text-gray-400 block">Approval Threshold (M)</label>
                                            <div className="flex items-center gap-4">
                                                <input
                                                    type="number"
                                                    min="2"
                                                    value={newThreshold}
                                                    onChange={(e) => setNewThreshold(e.target.value)}
                                                    className="w-24 bg-[#0a0a0a] border border-white/[0.08] rounded-lg px-4 py-2.5 text-center text-white font-mono text-lg focus:outline-none focus:border-red-500/40 focus:ring-1 focus:ring-red-500/30 shadow-inner"
                                                    required
                                                />
                                                <span className="text-xs text-gray-500">
                                                    of <span className="text-gray-300 font-bold">{newMembers.split(',').filter(Boolean).length + 1}</span> members required to unlock
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className="space-y-1.5">
                                        <label className="text-xs text-gray-400 block">Keyholders (excluding you)</label>
                                        <input
                                            type="text"
                                            value={newMembers}
                                            onChange={(e) => setNewMembers(e.target.value)}
                                            className="w-full bg-[#0a0a0a] border border-white/[0.08] rounded-lg px-4 py-3 text-sm text-white focus:outline-none focus:border-red-500/40 focus:ring-1 focus:ring-red-500/30 font-mono shadow-inner transition-colors placeholder:text-gray-700"
                                            required
                                            placeholder="agent_alpha, root_sec"
                                        />
                                        <p className="text-[10px] text-gray-600 mt-1.5">
                                            Comma-separated usernames. You will automatically be included.
                                        </p>
                                    </div>
                                    <div className="flex justify-end pt-2">
                                        <Button type="submit" variant="neon" className="px-6">
                                            Generate Vault & Distribute Keys
                                        </Button>
                                    </div>
                                </form>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* Boardroom Grid */}
            {isLoading ? (
                <div className="flex-1 flex items-center justify-center">
                    <Activity className="h-6 w-6 text-gray-600 animate-spin" />
                </div>
            ) : boardrooms.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-16 border border-white/[0.04] bg-white/[0.01] rounded-xl border-dashed">
                    <Users className="h-10 w-10 text-gray-700 mb-3" />
                    <p className="text-gray-600 text-sm">No active boardrooms. Create one to get started.</p>
                </div>
            ) : (
                <motion.div
                    className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3"
                    initial="hidden" animate="visible"
                    variants={{ hidden: { opacity: 0 }, visible: { opacity: 1, transition: { staggerChildren: 0.04 } } }}
                >
                    {(boardrooms || []).map((br) => (
                        <motion.div key={br.id} variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }}>
                            <Card
                                onClick={() => navigate(`/boardroom/${br.id}`)}
                                className="group cursor-pointer border-white/[0.04] bg-[#050505] hover:bg-[#0a0a0a] hover:border-white/[0.12] hover:-translate-y-1 hover:shadow-[0_12px_40px_-10px_rgba(0,0,0,0.8)] transition-all duration-300 relative h-full flex flex-col border-l-2 border-l-red-500/20"
                            >
                                <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-white/[0.06] to-transparent group-hover:via-red-500/40 transition-colors duration-500" />
                                <CardContent className="p-4 flex-1 flex flex-col">
                                    <div className="flex justify-between items-start mb-3">
                                        <div className="p-1.5 bg-white/[0.04] rounded-md">
                                            <Users className="h-5 w-5 text-gray-500" />
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded border text-white/60 border-white/10 bg-white/[0.04] font-mono">
                                                {br.threshold_m}/{br.total_members}
                                            </span>
                                        </div>
                                    </div>
                                    <h3 className="font-medium text-sm text-gray-200 truncate mb-1">{br.name}</h3>
                                    <div className="text-[10px] text-gray-500 mb-3 flex items-center gap-1">
                                        <Users className="h-3 w-3 text-gray-600" />{br.total_members} keyholders
                                    </div>
                                </CardContent>
                                <div className="border-t border-white/[0.04] bg-black/40 p-2 flex items-center justify-between px-4 opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                                    <span className="text-[10px] text-gray-600">Enter boardroom</span>
                                    <ChevronRight className="h-3.5 w-3.5 text-gray-600 group-hover:text-white group-hover:translate-x-0.5 transition-all" />
                                </div>
                            </Card>
                        </motion.div>
                    ))}
                </motion.div>
            )}
        </div>
    );
}
