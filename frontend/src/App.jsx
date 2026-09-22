import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Workspace from "./pages/Workspace";
import Home from "./pages/Home";
import About from "./pages/About";
import TopBar from "./components/TopBar";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return <div className="app-shell loading-screen">Loading…</div>;
  }

  return (
    <div className="app-shell">
      {user ? (
        <>
          <TopBar />
          <Routes>
            <Route path="/home" element={<Home />} />
            <Route path="/about" element={<About />} />
            <Route path="/workspace" element={<Dashboard />} />
            <Route path="/workspace/:workspaceId" element={<Workspace />} />
            <Route path="/" element={<Navigate to="/home" replace />} />
            <Route path="*" element={<Navigate to="/home" replace />} />
          </Routes>
        </>
      ) : (
        <Login />
      )}
    </div>
  );
}
