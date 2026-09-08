import { Navigate, Route, Routes } from 'react-router-dom'
import ErrorBoundary from './components/ErrorBoundary'
import Loading from './components/Loading'
import { useAuth } from './hooks/useAuth'
import AgentRunDetail from './pages/AgentRunDetail'
import AgentRuns from './pages/AgentRuns'
import AgentTemplates from './pages/AgentTemplates'
import FilesWorkbench from './pages/FilesWorkbench'
import Login from './pages/Login'
import MemoryWorkbench from './pages/MemoryWorkbench'
import ChatView from './pages/chat/ChatView'
import ProjectDetail from './pages/chat/ProjectDetail'
import Projects from './pages/chat/Projects'
import Register from './pages/Register'
import Settings from './pages/Settings'
import SkillsCatalog from './pages/SkillsCatalog'
import ToolRegistry from './pages/ToolRegistry'
import WorkbenchHome from './pages/WorkbenchHome'

function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading, error } = useAuth()

  if (isLoading) {
    return <Loading fullScreen text="正在恢复你的会话..." />
  }

  if (error) {
    return <Loading fullScreen text={`会话检查失败：${error.message}`} />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return children
}

function PublicOnlyRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return <Loading fullScreen text="正在检查登录状态..." />
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return children
}

export default function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/" element={<ProtectedRoute><ChatView /></ProtectedRoute>} />
        <Route path="/chat/:convId" element={<ProtectedRoute><ChatView /></ProtectedRoute>} />
        <Route path="/projects" element={<ProtectedRoute><Projects /></ProtectedRoute>} />
        <Route path="/projects/:projectId" element={<ProtectedRoute><ProjectDetail /></ProtectedRoute>} />
        <Route path="/agent" element={<ProtectedRoute><WorkbenchHome /></ProtectedRoute>} />
        <Route path="/runs" element={<ProtectedRoute><AgentRuns /></ProtectedRoute>} />
        <Route path="/runs/:runId" element={<ProtectedRoute><AgentRunDetail /></ProtectedRoute>} />
        <Route path="/templates" element={<ProtectedRoute><AgentTemplates /></ProtectedRoute>} />
        <Route path="/tools" element={<ProtectedRoute><ToolRegistry /></ProtectedRoute>} />
        <Route path="/files" element={<ProtectedRoute><FilesWorkbench /></ProtectedRoute>} />
        <Route path="/memories" element={<ProtectedRoute><MemoryWorkbench /></ProtectedRoute>} />
        <Route path="/skills" element={<ProtectedRoute><SkillsCatalog /></ProtectedRoute>} />
        <Route path="/settings" element={<ProtectedRoute><Settings /></ProtectedRoute>} />
        <Route path="/login" element={<PublicOnlyRoute><Login /></PublicOnlyRoute>} />
        <Route path="/register" element={<PublicOnlyRoute><Register /></PublicOnlyRoute>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </ErrorBoundary>
  )
}
