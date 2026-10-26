import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import Layout from "./Layout";
import { AgentProvider, AuthProvider, useAuth } from "./state";
import { Spinner } from "./ui";
import Login from "./pages/Login";
import Overview from "./pages/Overview";
import Courtroom from "./pages/Courtroom";
import Trap from "./pages/Trap";
import Watchman from "./pages/Watchman";
import Constitution from "./pages/Constitution";
import Guardian from "./pages/Guardian";
import DataFlow from "./pages/DataFlow";
import Emergency from "./pages/Emergency";
import RedTeam from "./pages/RedTeam";
import Audit from "./pages/Audit";
import Assistant from "./pages/Assistant";

function Gate() {
  const { user, loading } = useAuth();
  if (loading) return <div className="p-10"><Spinner /></div>;
  if (!user) return <Login />;
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="courtroom" element={<Courtroom />} />
        <Route path="trap" element={<Trap />} />
        <Route path="watchman" element={<Watchman />} />
        <Route path="constitution" element={<Constitution />} />
        <Route path="guardian" element={<Guardian />} />
        <Route path="data-flow" element={<DataFlow />} />
        <Route path="emergency" element={<Emergency />} />
        <Route path="red-team" element={<RedTeam />} />
        <Route path="audit" element={<Audit />} />
        <Route path="assistant" element={<Assistant />} />
        <Route path="*" element={<Navigate to="/" />} />
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
