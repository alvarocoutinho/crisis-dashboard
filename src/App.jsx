import { BrowserRouter, Routes, Route } from "react-router-dom";
import Landing from "./Landing";
import Live from "./Live";
import Archive from "./Archive";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/archive" element={<Archive />} />
        <Route path="/live" element={<Live />} />
        {/* Fallback: qualquer rota desconhecida cai na landing */}
        <Route path="*" element={<Landing />} />
      </Routes>
    </BrowserRouter>
  );
}
