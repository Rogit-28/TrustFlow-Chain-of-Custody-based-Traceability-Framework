import React, { useState } from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useToast } from '../components/ui/toast';
import { useAuth } from '../App';
import { Shield, User, Mail, Lock, ArrowRight, Activity } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';

export default function AuthView() {
    const [isLogin, setIsLogin] = useState(true);
    const [isLoading, setIsLoading] = useState(false);
    const { login, register } = useAuth();
    const toast = useToast();
    const [formData, setFormData] = useState({ username: '', email: '', password: '' });

    const handleSubmit = async (e) => {
        e.preventDefault();
        setIsLoading(true);
        try {
            if (isLogin) {
                await login(formData.username, formData.password);
                toast({ title: 'Authenticated', description: 'Session established.', type: 'success' });
            } else {
                await register(formData.username, formData.email, formData.password);
                toast({ title: 'Identity created', description: 'Ed25519 keypair generated. Sign in now.', type: 'success' });
                setIsLogin(true);
                setFormData(p => ({ ...p, password: '' }));
            }
        } catch (err) {
            toast({ title: 'Error', description: err.response?.data?.detail || err.message, type: 'error' });
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="min-h-screen flex items-center justify-center relative overflow-hidden bg-grid">
            {/* Faint red glow in corner */}
            <div className="absolute bottom-0 left-0 w-80 h-80 bg-red-500/[0.04] rounded-full blur-[100px] pointer-events-none" />

            <motion.div
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.4 }}
                className="w-full max-w-sm z-10 p-4"
            >
                {/* Brand */}
                <div className="flex flex-col items-center mb-8">
                    <motion.div
                        initial={{ y: -10, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.15 }}
                        className="p-3 rounded-xl border border-red-500/20 bg-red-500/5 mb-4 shadow-[0_0_25px_rgba(255,7,58,0.15)]"
                    >
                        <Shield className="h-8 w-8 text-red-500" />
                    </motion.div>
                    <motion.h1
                        initial={{ y: -8, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.25 }}
                        className="text-3xl font-display font-bold tracking-tight text-white"
                    >
                        TrustDocs
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.35 }}
                        className="text-gray-500 mt-1.5 text-sm"
                    >
                        Secure Document Collaboration
                    </motion.p>
                </div>

                <Card className="relative">
                    {/* Red accent line */}
                    <div className="absolute top-0 left-0 w-full h-px bg-gradient-to-r from-transparent via-red-500/40 to-transparent" />

                    <CardHeader>
                        <CardTitle className="text-lg">{isLogin ? 'Sign In' : 'Create Identity'}</CardTitle>
                        <CardDescription>
                            {isLogin ? 'Access your workspace.' : 'Generate your Ed25519 keys.'}
                        </CardDescription>
                    </CardHeader>

                    <form onSubmit={handleSubmit}>
                        <CardContent className="space-y-3">
                            <AnimatePresence mode="popLayout">
                                <motion.div key="username" layout initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}>
                                    <Input icon={User} placeholder="Username" required value={formData.username}
                                        onChange={e => setFormData({ ...formData, username: e.target.value })} />
                                </motion.div>
                                {!isLogin && (
                                    <motion.div key="email" layout initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }}>
                                        <Input type="email" icon={Mail} placeholder="Email" required={!isLogin} value={formData.email}
                                            onChange={e => setFormData({ ...formData, email: e.target.value })} />
                                    </motion.div>
                                )}
                                <motion.div key="password" layout initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }}>
                                    <Input type="password" icon={Lock} placeholder="Password" required value={formData.password}
                                        onChange={e => setFormData({ ...formData, password: e.target.value })} />
                                </motion.div>
                            </AnimatePresence>
                        </CardContent>

                        <CardFooter className="flex flex-col gap-3">
                            <Button type="submit" className="w-full" size="lg" isLoading={isLoading}>
                                {isLogin ? 'Authenticate' : 'Generate Keys'}
                                {!isLoading && <ArrowRight className="ml-2 h-4 w-4" />}
                            </Button>
                            <div className="text-xs text-gray-500 text-center">
                                {isLogin ? "No identity? " : "Already registered? "}
                                <button type="button" onClick={() => setIsLogin(!isLogin)}
                                    className="text-white hover:text-red-400 font-medium transition-colors cursor-pointer">
                                    {isLogin ? 'Register.' : 'Sign in.'}
                                </button>
                            </div>
                        </CardFooter>
                    </form>
                </Card>

                <div className="mt-6 text-center flex items-center justify-center gap-1.5 text-[10px] text-gray-600 uppercase tracking-widest">
                    <Activity className="h-3 w-3" /> TrustFlow Framework
                </div>
            </motion.div>
        </div>
    );
}
