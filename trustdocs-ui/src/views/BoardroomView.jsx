import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { useToast } from '../components/ui/toast';
import { Users, Plus, ShieldCheck, ChevronRight } from 'lucide-react';
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
        <div className="h-full flex flex-col max-w-5xl mx-auto space-y-6 lg:space-y-8">
            <div className="flex items-center justify-between shrink-0">
                <div className="flex items-center gap-3">
                    <Users className="h-7 w-7 text-emerald-500" />
                    <div>
                        <h1 className="text-2xl font-display font-bold text-white tracking-tight">Inner Circle</h1>
                        <p className="text-gray-500 text-sm mt-0.5">High-security boardrooms utilizing Shamir's Secret Sharing.</p>
                    </div>
                </div>
                <Button onClick={() => setIsCreating(!isCreating)} variant="neon" className="px-4">
                    {isCreating ? 'Cancel' : <><Plus className="h-4 w-4 mr-2" /> New Boardroom</>}
                </Button>
            </div>

            <AnimatePresence>
                {isCreating && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: 'auto' }}
                        exit={{ opacity: 0, height: 0 }}
                        className="overflow-hidden"
                    >
                        <Card className="bg-[#050505] border-white/[0.06] shadow-xl relative mt-4">
                            <div className="absolute top-0 right-0 w-64 h-64 bg-emerald-500/5 blur-3xl pointer-events-none rounded-full translate-x-1/4 -translate-y-1/4" />
                            <CardHeader className="pb-4">
                                <CardTitle className="text-lg flex items-center gap-2">
                                    <ShieldCheck className="h-5 w-5 text-emerald-500" /> Configure Threshold Execution
                                </CardTitle>
                                <CardDescription>
                                    Any execution documents uploaded to this boardroom will be cryptographically split. They can only be rebuilt if the threshold M of N is met.
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <form onSubmit={handleCreate} className="space-y-4">
                                    <div>
                                        <label className="text-xs font-medium text-gray-400 mb-1 block">Boardroom Name</label>
                                        <input
                                            type="text"
                                            value={newName}
                                            onChange={(e) => setNewName(e.target.value)}
                                            className="w-full bg-black border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50"
                                            required
                                            placeholder="e.g. Project Orion Executives"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-xs font-medium text-gray-400 mb-1 block">Member Usernames (excluding you)</label>
                                        <input
                                            type="text"
                                            value={newMembers}
                                            onChange={(e) => setNewMembers(e.target.value)}
                                            className="w-full bg-black border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50 font-mono"
                                            required
                                            placeholder="user2, user3"
                                        />
                                        <p className="text-[10px] text-gray-500 mt-1">Comma-separated exact usernames. You will automatically be included.</p>
                                    </div>
                                    <div className="flex gap-4 items-center">
                                        <div className="w-1/3">
                                            <label className="text-xs font-medium text-gray-400 mb-1 block">Approval Threshold (M)</label>
                                            <input
                                                type="number"
                                                min="2"
                                                value={newThreshold}
                                                onChange={(e) => setNewThreshold(e.target.value)}
                                                className="w-full bg-black border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500/50 focus:ring-1 focus:ring-emerald-500/50"
                                                required
                                            />
                                        </div>
                                        <div className="flex-1 text-xs text-gray-500 pt-5">
                                            Out of the {newMembers.split(',').filter(Boolean).length + 1} total members, <strong>{newThreshold}</strong> must approve proposals to unlock them.
                                        </div>
                                    </div>
                                    <div className="flex justify-end pt-4 border-t border-white/[0.04]">
                                        <Button type="submit" variant="neon" className="bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
                                            Initialize Secure Vault
                                        </Button>
                                    </div>
                                </form>
                            </CardContent>
                        </Card>
                    </motion.div>
                )}
            </AnimatePresence>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {isLoading ? (
                    <div className="col-span-full py-20 flex justify-center opacity-50">
                        <div className="h-8 w-8 rounded-full border-2 border-emerald-500/20 border-t-emerald-500 animate-spin" />
                    </div>
                ) : boardrooms.length === 0 ? (
                    <div className="col-span-full py-20 text-center text-gray-500 text-sm">
                        You are not a member of any Inner Circle boardrooms.
                    </div>
                ) : (
                    (boardrooms || []).map((br) => (
                        <Card
                            key={br.id}
                            onClick={() => navigate(`/boardroom/${br.id}`)}
                            className="bg-[#050505] border-white/[0.06] hover:border-emerald-500/30 transition-colors cursor-pointer group"
                        >
                            <CardHeader className="pb-2">
                                <CardTitle className="text-base text-gray-200 group-hover:text-emerald-400 transition-colors truncate">
                                    {br.name}
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="flex items-center justify-between text-xs text-gray-500">
                                    <div className="flex items-center gap-1.5">
                                        <Users className="h-3.5 w-3.5" />
                                        {br.total_members} members
                                    </div>
                                    <div className="bg-white/5 py-1 px-2 rounded flex items-center gap-1 font-mono text-[10px]">
                                        M-of-N: <span className="text-white">{br.threshold_m}/{br.total_members}</span>
                                    </div>
                                </div>
                            </CardContent>
                        </Card>
                    ))
                )}
            </div>
        </div>
    );
}
