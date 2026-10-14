import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Landing from "./Landing";
import Live from "./Live";
import Archive from "./Archive";

// Leaflet só é carregado quando /idap é aberto
const Idap = lazy(() => import("./Idap"));

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/archive" element={<Archive />} />
        <Route path="/live" element={<Live />} />
        <Route path="/idap" element={<Suspense fallback={null}><Idap /></Suspense>} />
        {/* Fallback: qualquer rota desconhecida cai na landing */}
        <Route path="*" element={<Landing />} />
      </Routes>
    </BrowserRouter>
  );
}
