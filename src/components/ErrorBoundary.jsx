import { Component } from "react";

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidUpdate(prevProps) {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  handleRetry = () => {
    this.setState({ error: null });
  };

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-5 text-red-100 shadow-lg shadow-black/10">
        <h2 className="text-sm font-semibold text-red-50">Erreur du module</h2>
        <p className="mt-2 text-xs text-red-100/90">
          {this.state.error?.message || "Une erreur inattendue est survenue."}
        </p>
        <button
          type="button"
          onClick={this.handleRetry}
          className="mt-4 rounded-lg border border-red-400/40 px-3 py-1.5 text-xs font-semibold text-red-50 transition-colors hover:bg-red-500/20"
        >
          Réessayer
        </button>
      </div>
    );
  }
}
