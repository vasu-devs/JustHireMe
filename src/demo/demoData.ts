export type DemoJob = {
  id: number;
  company: string;
  role: string;
  location: string;
  source: string;
  posted: string;
  score: number;
  signal: "Exceptional" | "Strong" | "Promising";
  stage: "Discovered" | "Tailored" | "Ready" | "Applied";
  salary: string;
  accent: string;
  reasons: string[];
};

export const demoJobs: DemoJob[] = [
  {
    id: 1,
    company: "Linear",
    role: "Senior Product Engineer",
    location: "Remote · Europe",
    source: "Hacker News",
    posted: "18m ago",
    score: 94,
    signal: "Exceptional",
    stage: "Ready",
    salary: "$170k–$220k",
    accent: "coral",
    reasons: ["TypeScript product depth", "0→1 ownership", "Async-first team"],
  },
  {
    id: 2,
    company: "Replit",
    role: "AI Product Engineer",
    location: "Remote · US overlap",
    source: "YC Jobs",
    posted: "42m ago",
    score: 91,
    signal: "Exceptional",
    stage: "Tailored",
    salary: "$180k–$240k",
    accent: "lime",
    reasons: ["Agent systems", "Developer tools", "Fast shipping cadence"],
  },
  {
    id: 3,
    company: "Mercury",
    role: "Staff Frontend Engineer",
    location: "Remote · Americas",
    source: "Company site",
    posted: "1h ago",
    score: 87,
    signal: "Strong",
    stage: "Discovered",
    salary: "$190k–$245k",
    accent: "blue",
    reasons: ["Design engineering", "Fintech experience", "React architecture"],
  },
  {
    id: 4,
    company: "Vercel",
    role: "Product Engineer, AI",
    location: "Remote · Global",
    source: "Ashby",
    posted: "3h ago",
    score: 84,
    signal: "Strong",
    stage: "Applied",
    salary: "$165k–$230k",
    accent: "sand",
    reasons: ["Next.js expertise", "AI interfaces", "Open-source work"],
  },
  {
    id: 5,
    company: "Granola",
    role: "Founding Full-stack Engineer",
    location: "London · Hybrid",
    source: "Wellfound",
    posted: "5h ago",
    score: 79,
    signal: "Promising",
    stage: "Discovered",
    salary: "£110k–£150k",
    accent: "pink",
    reasons: ["Early-stage range", "Desktop apps", "High product taste"],
  },
  {
    id: 6,
    company: "Supabase",
    role: "Developer Experience Engineer",
    location: "Remote · Global",
    source: "Company site",
    posted: "7h ago",
    score: 88,
    signal: "Strong",
    stage: "Tailored",
    salary: "$155k–$210k",
    accent: "lime",
    reasons: ["Open-source systems", "Developer education", "TypeScript depth"],
  },
  {
    id: 7,
    company: "Ramp",
    role: "Senior Software Engineer, Growth",
    location: "New York · Hybrid",
    source: "LinkedIn",
    posted: "9h ago",
    score: 82,
    signal: "Strong",
    stage: "Ready",
    salary: "$185k–$250k",
    accent: "blue",
    reasons: ["Growth infrastructure", "Product analytics", "High ownership"],
  },
  {
    id: 8,
    company: "Attio",
    role: "Product Engineer",
    location: "London · Hybrid",
    source: "Otta",
    posted: "12h ago",
    score: 76,
    signal: "Promising",
    stage: "Discovered",
    salary: "£95k–£135k",
    accent: "pink",
    reasons: ["Complex UI systems", "Design partnership", "Product-led culture"],
  },
];

export const activity = [
  { time: "09:42", label: "Application kit ready", detail: "Linear · Senior Product Engineer", tone: "ready" },
  { time: "09:39", label: "Resume evidence matched", detail: "7 claims grounded in your profile", tone: "match" },
  { time: "09:31", label: "New role discovered", detail: "Mercury · Staff Frontend Engineer", tone: "new" },
];
