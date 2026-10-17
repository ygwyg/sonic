import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import BenchmarkPage from "./pages/BenchmarkPage";
import ExplorerPage from "./pages/ExplorerPage";
import QrStudioPage from "./pages/QrStudioPage";
import ReceiverPage from "./pages/ReceiverPage";
import TransmitterPage from "./pages/TransmitterPage";

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Navigate to="/transmitter" replace />} />
        <Route path="/transmitter" element={<TransmitterPage />} />
        <Route path="/receiver" element={<ReceiverPage />} />
        <Route path="/explorer" element={<ExplorerPage />} />
        <Route path="/benchmark" element={<BenchmarkPage />} />
        <Route path="/qr" element={<QrStudioPage />} />
        <Route path="*" element={<Navigate to="/transmitter" replace />} />
      </Routes>
    </Layout>
  );
}
