import { BrowserRouter, Routes, Route } from "react-router-dom";
import Landing from "./Landing";
import Live from "./Live";
import Dashboard from "./dashboard";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/archive" element={<Dashboard />} />
        <Route path="/live" element={<Live />} />
        {/* Fallback: qualquer rota desconhecida cai na landing */}
        <Route path="*" element={<Landing />} />
      </Routes>
    </BrowserRouter>
  );
}
