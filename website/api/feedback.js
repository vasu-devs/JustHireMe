import { json, send } from "./_counter.js";

const DEFAULT_REPO = "vasu-devs/JustHireMe";
const VALID_KINDS = new Set(["feedback", "review"]);
const EMAIL_RE = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi;
const PHONE_RE = /(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)/g;
const SECRET_RE = /(ghp_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|Bearer\s+[A-Za-z0-9._~+/=-]{10,})/g;

function cleanText(value, limit) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, limit);
}

function cleanMultiline(value, limit) {
  return String(value || "").replace(/\r\n/g, "\n").replace(/\n{4,}/g, "\n\n\n").trim().slice(0, limit);
}

export function redactPublicText(value, limit) {
  return cleanMultiline(value, limit)
    .replace(SECRET_RE, "[REDACTED_SECRET]")
    .replace(EMAIL_RE, "[REDACTED_EMAIL]")
    .replace(PHONE_RE, "[REDACTED_PHONE]");
}

function issueTitle(kind, rating) {
  const prefix = kind === "review" ? "Website review" : "Website feedback";
  const score = kind === "review" && rating ? ` (${rating}/5)` : "";
  return `${prefix}${score}`;
}

function buildBody({ kind, nameProvided, emailProvided, rating, message, path }) {
  const lines = [
    `Kind: ${kind}`,
    nameProvided ? "Name: provided, redacted from public issue" : null,
    emailProvided ? "Email: provided, redacted from public issue" : null,
    kind === "review" && rating ? `Rating: ${rating}/5` : null,
    path ? `Page: ${path}` : null,
    "",
    message,
  ].filter((line) => line !== null);

  return lines.join("\n");
}

async function addIssueLabels(repo, issueNumber, token, kind) {
  const labels = ["website-feedback", kind === "review" ? "review" : "feedback"];

  const response = await fetch(`https://api.github.com/repos/${repo}/issues/${issueNumber}/labels`, {
    method: "POST",
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "user-agent": "justhireme-website",
    },
    body: JSON.stringify({ labels }),
  });

  if (!response.ok) {
    return false;
  }

  return true;
}

async function createGitHubIssue(payload) {
  const token = process.env.GITHUB_FEEDBACK_TOKEN || process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_FEEDBACK_REPO || DEFAULT_REPO;

  if (!token) {
    return null;
  }

  const response = await fetch(`https://api.github.com/repos/${repo}/issues`, {
    method: "POST",
    headers: {
      accept: "application/vnd.github+json",
      authorization: `Bearer ${token}`,
      "content-type": "application/json",
      "user-agent": "justhireme-website",
    },
    body: JSON.stringify({
      title: issueTitle(payload.kind, payload.rating),
      body: buildBody(payload),
    }),
  });

  if (!response.ok) {
    throw new Error(`GitHub issue creation failed with ${response.status}`);
  }

  const issue = await response.json();
  const labeled = await addIssueLabels(repo, issue.number, token, payload.kind).catch(() => false);
  return { provider: "github", url: issue.html_url, labeled };
}

export default async function handler(request, response) {
  if (request.method !== "POST") {
    return send(response, json({ error: "Method not allowed" }, 405));
  }

  try {
    const body = typeof request.body === "object" && request.body ? request.body : {};

    if (body.website) {
      return send(response, json({ delivered: true, ignored: true }));
    }

    const kind = VALID_KINDS.has(body.kind) ? body.kind : "feedback";
    const message = redactPublicText(body.message, 5000);
    const rating = Math.max(1, Math.min(5, Number.parseInt(body.rating || "0", 10) || 0));

    if (message.length < 8) {
      return send(response, json({ error: "Please add a little more detail." }, 400));
    }

    const payload = {
      kind,
      nameProvided: Boolean(cleanText(body.name, 120)),
      emailProvided: Boolean(cleanText(body.email, 160)),
      rating: kind === "review" ? rating : null,
      message,
      path: cleanText(body.path, 220),
    };

    const issue = await createGitHubIssue(payload);

    if (!issue) {
      return send(response, json({
        delivered: false,
        deliveries: [],
        configured: false,
      }, 202));
    }

    return send(response, json({
      delivered: true,
      deliveries: [issue],
      configured: true,
    }));
  } catch (error) {
    if (error.message?.startsWith("GitHub issue creation failed")) {
      return send(response, json({ error: "Feedback delivery is unavailable right now." }, 500));
    }

    return send(response, json({ error: "Feedback delivery is unavailable right now." }, 500));
  }
}
