import React from 'react';
import { cn } from '../../lib/utils';
import { Loader2 } from 'lucide-react';
import { motion } from 'framer-motion';

const Button = React.forwardRef(({ className, variant = 'primary', size = 'default', isLoading = false, children, ...props }, ref) => {
    const variants = {
        primary: 'bg-white text-black font-semibold hover:bg-gray-200 border border-white/80',
        secondary: 'bg-white/5 text-white hover:bg-white/10 border border-white/10',
        danger: 'bg-transparent text-red-500 hover:bg-red-500/10 border border-red-500/40 shadow-[0_0_10px_rgba(255,7,58,0.15)]',
        ghost: 'hover:bg-white/5 text-gray-400 hover:text-white',
        neon: 'bg-transparent text-red-500 border border-red-500/60 hover:bg-red-500/10 shadow-[0_0_15px_rgba(255,7,58,0.25)] hover:shadow-[0_0_25px_rgba(255,7,58,0.4)]',
    };

    const sizes = {
        default: 'h-10 px-4 py-2',
        sm: 'h-9 px-3 text-sm',
        lg: 'h-11 px-8',
        icon: 'h-10 w-10 p-2',
    };

    return (
        <motion.button
            ref={ref}
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.98 }}
            className={cn(
                'inline-flex items-center justify-center rounded-lg text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-red-500/30 disabled:pointer-events-none disabled:opacity-40 relative overflow-hidden cursor-pointer',
                variants[variant],
                sizes[size],
                className
            )}
            disabled={isLoading || props.disabled}
            {...props}
        >
            {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {children}
        </motion.button>
    );
});

Button.displayName = 'Button';
export { Button };
