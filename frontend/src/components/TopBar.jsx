import { NavLink, Link, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function TopBar() {
  const { user, signOut } = useAuth();
  const location = useLocation();
  const name = user?.displayName || user?.email || "";

  const isWorkspaceActive = location.pathname.startsWith("/workspace");

  return (
    <header className="topbar">
      <div className="topbar-left">
        <Link to="/home" className="topbar-brand">
          Research Paper Assistant
        </Link>
        <nav className="topbar-nav" aria-label="Main Navigation">
          <NavLink
            to="/home"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            Home
          </NavLink>
          <NavLink
            to="/about"
            className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
          >
            About
          </NavLink>
          <NavLink
            to="/workspace"
            className={() => (isWorkspaceActive ? "nav-link active" : "nav-link")}
          >
            Workspace
          </NavLink>
        </nav>
      </div>

      <div className="topbar-right">
        {name && <span className="topbar-user">{name}</span>}
        <button className="btn-ghost" onClick={signOut}>
          Sign out
        </button>
      </div>
    </header>
  );
}
