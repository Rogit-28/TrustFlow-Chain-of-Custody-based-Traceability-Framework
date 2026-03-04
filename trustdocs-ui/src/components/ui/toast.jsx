import React from 'react';
import { cn } from '../../lib/utils';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, CheckCircle2 } from 'lucide-react';

export const ToastContext = React.createContext(() => { });
export const useToast = () => React.useContext(ToastContext);

export const ToastProvider = ({ children }) => {
    const [toasts, setToasts] = React.useState([]);

    const toast = React.useCallback(({ title, description, type = 'default' }) => {
        const id = Math.random().toString(36).substring(2, 9);
        setToasts((prev) => [...prev, { id, title, description, type }]);
        setTimeout(() => {
            setToasts((prev) => prev.filter((t) => t.id !== id));
        }, 5000);
    }, []);

    return (
        <ToastContext.Provider value={toast}>
            {children}
            <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 w-full max-w-sm">
                <AnimatePresence>
                    {toasts.map((t) => (
                        <Toast key={t.id} {...t} onDismiss={() => setToasts(p => p.filter(x => x.id !== t.id))} />
                    ))}
                </AnimatePresence>
            </div>
        </ToastContext.Provider>
    );
};

const Toast = ({ title, description, type, onDismiss }) => {
    const isError = type === 'error';
    const isSuccess = type === 'success';

    return (
        <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95, transition: { duration: 0.2 } }}
            onClick={onDismiss}
            className={cn(
                "cursor-pointer pointer-events-auto flex w-full items-start gap-3 rounded-xl border p-4 shadow-2xl transition-all bg-[#0a0a0a]",
                isError ? "border-red-500/30 shadow-[0_0_20px_rgba(255,7,58,0.15)]" :
                    isSuccess ? "border-emerald-500/30" :
                        "border-white/10"
            )}
        >
            {isError && <AlertCircle className="h-5 w-5 text-red-500 mt-0.5 shrink-0" />}
            {isSuccess && <CheckCircle2 className="h-5 w-5 text-emerald-400 mt-0.5 shrink-0" />}
            <div className="flex flex-col gap-1">
                {title && <div className="text-sm font-semibold text-white">{title}</div>}
                {description && <div className="text-sm text-gray-400">{description}</div>}
            </div>
        </motion.div>
    );
};
