import {
  ArrowUp,
  BookOpen,
  Check,
  ChevronDown,
  Copy,
  Download,
  FileText,
  FlaskConical,
  Folder,
  Globe,
  List,
  LogOut,
  MessageCircle,
  Moon,
  Paperclip,
  Pencil,
  Plus,
  RotateCw,
  Settings,
  Sparkles,
  Square,
  Star,
  Sun,
  Trash2,
  User,
  X,
} from 'lucide-react'

// lucide 图标映射：保持 name/size/strokeWidth/className 的旧 API，
// 全站调用方无需感知底层图标库。
const icons = {
  chat: MessageCircle,
  folder: Folder,
  task: List,
  spark: Sparkles,
  gear: Settings,
  book: BookOpen,
  flask: FlaskConical,
  trash: Trash2,
  plus: Plus,
  arrowUp: ArrowUp,
  stop: Square,
  paperclip: Paperclip,
  chevron: ChevronDown,
  check: Check,
  x: X,
  logout: LogOut,
  file: FileText,
  user: User,
  refresh: RotateCw,
  globe: Globe,
  rename: Pencil,
  copy: Copy,
  moon: Moon,
  sun: Sun,
  star: Star,
  download: Download,
}

export default function Icon({ name, size = 16, strokeWidth = 1.8, className = '' }) {
  const Glyph = icons[name]
  if (!Glyph) return null
  return (
    <Glyph
      className={`icon ${className}`}
      size={size}
      strokeWidth={strokeWidth}
      aria-hidden="true"
    />
  )
}

export function BrandMark({ size = 26 }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect width="24" height="24" rx="6" fill="currentColor" />
      <path
        d="M8 6.5v11M16 6.5v11M8 12h8"
        stroke="var(--bg, #fff)"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  )
}
