export default function FileUploader({ disabled, onFiles }) {
  return (
    <label className={`file-uploader ${disabled ? 'disabled' : ''}`}>
      <input
        type="file"
        multiple
        accept=".pdf,.doc,.docx,.txt,.md"
        disabled={disabled}
        onChange={(event) => {
          if (event.target.files?.length) {
            onFiles?.(event.target.files)
            event.target.value = ''
          }
        }}
      />
      <span>添加资料</span>
    </label>
  )
}
