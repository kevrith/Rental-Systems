import DOMPurify from 'dompurify'
import { Bold, Heading2, Italic, List, ListOrdered, Redo2, Undo2 } from 'lucide-react'
import { useEffect, useRef } from 'react'

import { Button } from '@/components/ui'
import { cn } from '@/lib/cn'

interface Command {
  label: string
  icon: React.ReactNode
  command: string
  value?: string
}

const COMMANDS: Command[] = [
  { label: 'Bold', icon: <Bold className="h-4 w-4" />, command: 'bold' },
  { label: 'Italic', icon: <Italic className="h-4 w-4" />, command: 'italic' },
  { label: 'Heading', icon: <Heading2 className="h-4 w-4" />, command: 'formatBlock', value: 'h3' },
  { label: 'Bulleted list', icon: <List className="h-4 w-4" />, command: 'insertUnorderedList' },
  {
    label: 'Numbered list',
    icon: <ListOrdered className="h-4 w-4" />,
    command: 'insertOrderedList',
  },
  { label: 'Undo', icon: <Undo2 className="h-4 w-4" />, command: 'undo' },
  { label: 'Redo', icon: <Redo2 className="h-4 w-4" />, command: 'redo' },
]

/**
 * A small rich-text editor over `contentEditable` (US-047).
 *
 * The lease body is stored as HTML and rendered through WeasyPrint, so the
 * editor's job is to produce clean, simple markup — headings, emphasis, lists —
 * not to be a word processor. `document.execCommand` is deprecated but is the
 * only thing every browser still implements without a dependency; the raw-HTML
 * tab below is the escape hatch when it produces something unwanted.
 *
 * The DOM is only written from `value` when the two have actually diverged.
 * Assigning `innerHTML` on every render would move the caret to the start of the
 * document on each keystroke.
 *
 * `value` is run through DOMPurify before that assignment: the raw-HTML tab
 * mentioned above lets a landlord type arbitrary markup directly, and this
 * component reinterprets whatever lands in `value` as HTML the moment it's
 * shown — an `<img onerror>` typed there (or pasted from somewhere untrusted)
 * would otherwise execute in the editor immediately, not just in whatever
 * eventually renders the saved lease.
 */
export function RichTextEditor({
  value,
  onChange,
  onInsertPoint,
  className,
}: {
  value: string
  onChange: (html: string) => void
  /** Called with a function that inserts text where the caret is. */
  onInsertPoint?: (insert: (text: string) => void) => void
  className?: string
}) {
  const editorRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const node = editorRef.current
    if (!node) return
    const sanitized = DOMPurify.sanitize(value)
    if (node.innerHTML !== sanitized) node.innerHTML = sanitized
  }, [value])

  useEffect(() => {
    if (!onInsertPoint) return
    onInsertPoint((text: string) => {
      const node = editorRef.current
      if (!node) return
      node.focus()
      const selection = window.getSelection()
      // Only splice into the caret when the caret is actually inside the editor;
      // otherwise a click on the variable list would insert into the page body.
      if (selection?.rangeCount && node.contains(selection.anchorNode)) {
        const range = selection.getRangeAt(0)
        range.deleteContents()
        range.insertNode(document.createTextNode(text))
        range.collapse(false)
      } else {
        node.append(document.createTextNode(text))
      }
      onChange(node.innerHTML)
    })
  }, [onInsertPoint, onChange])

  const run = (command: Command) => {
    editorRef.current?.focus()
    document.execCommand(command.command, false, command.value)
    if (editorRef.current) onChange(editorRef.current.innerHTML)
  }

  return (
    <div className={cn('rounded-card border border-slate-200', className)}>
      <div className="flex flex-wrap gap-0.5 border-b border-slate-200 bg-slate-50 p-1.5">
        {COMMANDS.map((command) => (
          <Button
            key={command.label}
            type="button"
            size="sm"
            variant="ghost"
            aria-label={command.label}
            title={command.label}
            onClick={() => run(command)}
          >
            {command.icon}
          </Button>
        ))}
      </div>
      <div
        ref={editorRef}
        contentEditable
        suppressContentEditableWarning
        role="textbox"
        aria-multiline="true"
        aria-label="Lease body"
        onInput={(event) => onChange(event.currentTarget.innerHTML)}
        className="prose-sm min-h-[24rem] max-w-none overflow-y-auto p-4 text-sm leading-relaxed text-slate-800 focus:outline-none [&_h2]:mb-2 [&_h2]:mt-4 [&_h2]:text-base [&_h2]:font-semibold [&_h3]:mb-1.5 [&_h3]:mt-3 [&_h3]:font-semibold [&_li]:ml-5 [&_li]:list-disc [&_ol_li]:list-decimal [&_p]:mb-2"
      />
    </div>
  )
}
