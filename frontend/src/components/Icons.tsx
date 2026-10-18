type P = { size?: number };
const base = (size = 16) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
});

export const Check = ({ size }: P) => (<svg {...base(size)}><path d="M20 6 9 17l-5-5" /></svg>);
export const Alert = ({ size }: P) => (<svg {...base(size)}><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" /></svg>);
export const X = ({ size }: P) => (<svg {...base(size)}><path d="M18 6 6 18M6 6l12 12" /></svg>);
export const Send = ({ size }: P) => (<svg {...base(size)}><path d="m22 2-7 20-4-9-9-4z" /><path d="M22 2 11 13" /></svg>);
export const Chevron = ({ size }: P) => (<svg {...base(size)}><path d="m6 9 6 6 6-6" /></svg>);
export const Clock = ({ size }: P) => (<svg {...base(size)}><circle cx="12" cy="12" r="10" /><path d="M12 6v6l4 2" /></svg>);
export const Coins = ({ size }: P) => (<svg {...base(size)}><circle cx="8" cy="8" r="6" /><path d="M18.1 10.4A6 6 0 1 1 10.3 18" /></svg>);
export const Zap = ({ size }: P) => (<svg {...base(size)}><path d="M13 2 3 14h9l-1 8 10-12h-9z" /></svg>);
export const Database = ({ size }: P) => (<svg {...base(size)}><ellipse cx="12" cy="5" rx="9" ry="3" /><path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5" /><path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3" /></svg>);
export const Sun = ({ size }: P) => (<svg {...base(size)}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>);
export const Moon = ({ size }: P) => (<svg {...base(size)}><path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z" /></svg>);
export const Shield = ({ size }: P) => (<svg {...base(size)}><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" /><path d="m9 12 2 2 4-4" /></svg>);
export const External = ({ size }: P) => (<svg {...base(size)}><path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg>);
export const Refresh = ({ size }: P) => (<svg {...base(size)}><path d="M21 12a9 9 0 1 1-3-6.7L21 8" /><path d="M21 3v5h-5" /></svg>);
