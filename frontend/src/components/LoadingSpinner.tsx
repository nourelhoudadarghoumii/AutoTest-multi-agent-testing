interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  fullScreen?: boolean;
  message?: string;
}

export default function LoadingSpinner({ size = 'md', fullScreen = false, message }: LoadingSpinnerProps) {
  const sizeClasses = {
    sm: 'w-4 h-4 border-2',
    md: 'w-7 h-7 border-2',
    lg: 'w-10 h-10 border-[3px]',
  };

  const spinner = (
    <div className="flex flex-col items-center justify-center gap-3 py-10">
      <div className={`${sizeClasses[size]} border-cap-200 border-t-cap-500 rounded-full animate-spin`} />
      {message && <p className="text-xs font-mono text-slate2-500 uppercase tracking-wider">{message}</p>}
    </div>
  );

  if (fullScreen) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate2-50">
        {spinner}
      </div>
    );
  }

  return spinner;
}
