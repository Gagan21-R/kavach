import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import "./index.css";
import Layout from "./Layout";
import { AgentProvider, AuthProvider, useAuth } from "./state";
import { Spinner } from "./ui";
import Login from "./pages/Login";
import Dashboard from "./Dashboard";
import Onboarding from "./pages/Onboarding";

function Gate() {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-10"><Spinner /></div>;
  if (!user) return <Login />;
  if (!user.onboarded) return <Onboarding />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="*" element={<Dashboard />} />
      </Route>
    </Routes>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <AgentProvider>
          <Gate />
        </AgentProvider>
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
