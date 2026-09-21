import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function TopBar() {
  const { user, signOut } = useAuth();
  const name = user?.displayName || user?.email || "";

  return (
    <header className="topbar">
      <Link to="/" className="topbar-brand">
        Research Paper Assistant
      </Link>
      <div className="topbar-right">
        {name && <span className="topbar-user">{name}</span>}
        <button className="btn-ghost" onClick={signOut}>
          Sign out
        </button>
      </div>
    </header>
  );
}
