import DOMPurify from 'dompurify';
import { marked } from 'marked';

marked.use({
  gfm: true,
  breaks: false,
  headerIds: false,
  mangle: false,
});

export function renderMarkdown(markdown) {
  return DOMPurify.sanitize(marked.parse(markdown || ''), {
    USE_PROFILES: { html: true },
  });
}
