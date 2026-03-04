import React from 'react';
import { cn } from '../../lib/utils';

const Input = React.forwardRef(({ className, type, icon: Icon, ...props }, ref) => {
    return (
        <div className="relative">
            {Icon && (
                <div className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
                    <Icon className="h-4 w-4" />
                </div>
            )}
            <input
                type={type}
                className={cn(
                    "flex h-11 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white placeholder:text-gray-600 transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-red-500/40 focus-visible:border-red-500/40 disabled:cursor-not-allowed disabled:opacity-50",
                    Icon && "pl-10",
                    className
                )}
                ref={ref}
                {...props}
            />
        </div>
    )
})
Input.displayName = "Input"
export { Input }
