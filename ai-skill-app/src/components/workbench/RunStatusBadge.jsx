export default function RunStatusBadge({ status = 'pending' }) {
  return (
    <span className={`status-badge ${status}`}>
      {formatStatus(status)}
    </span>
  )
}

function formatStatus(status) {
  switch (status) {
    case 'running':
      return '运行中'
    case 'done':
      return '已完成'
    case 'failed':
      return '失败'
    case 'cancelled':
      return '已取消'
    default:
      return '待执行'
  }
}
