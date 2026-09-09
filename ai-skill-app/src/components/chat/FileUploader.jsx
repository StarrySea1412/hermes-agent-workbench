import Icon from '../Icon'

export default function FileUploader({ disabled, onFiles, withIcon = false }) {
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
      {withIcon ? <Icon name="paperclip" size={13} /> : null}
      <span>添加资料</span>
    </label>
  )
}
