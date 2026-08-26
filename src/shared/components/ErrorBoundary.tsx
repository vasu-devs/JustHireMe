import React from "react";
import { diagnosticsApi } from "../../api";

class ErrorBoundary extends React.Component<
  { children: React.ReactNode; label: string; api?: (path: string, opts?: RequestInit) => Promise<Response> },
  { error: Error | null; retryCount: number }
> {
  state = { error: null, retryCount: 0 };

  static getDerivedStateFromError(e: Error) {
    return { error: e };
  }

  componentDidCatch(e: Error, info: React.ErrorInfo) {
    console.error(`[ErrorBoundary:${this.props.label}]`, e, info);
    const api = this.props.api;
    if (api) {
      diagnosticsApi.reportError(api, {
        error: e.message,
        componentStack: info.componentStack ?? "",
        label: this.props.label,
      }).catch(() => {});
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{
          display: "flex", flexDirection: "column", alignItems: "center",
          justifyContent: "center", height: "100%", gap: 12, opacity: 0.6,
        }}>
          <p style={{ margin: 0, fontSize: 14 }}>
            {this.props.label} failed to load.
          </p>
          <button onClick={() => this.setState(prev => ({ error: null, retryCount: prev.retryCount + 1 }))}
            style={{ fontSize: 12 }}>
            Retry
          </button>
        </div>
      );
    }
    return <React.Fragment key={this.state.retryCount}>{this.props.children}</React.Fragment>;
  }
}

export default ErrorBoundary;
