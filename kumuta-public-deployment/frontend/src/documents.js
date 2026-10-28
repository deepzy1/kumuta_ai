export const DOCUMENT_ACCEPT = '.pdf,.docx,.txt,.md,.markdown';
export function validateDocuments(files) {
  if (!files.length) return 'Choose a document.';
  if (files.length > 5) return 'Upload up to 5 documents at a time.';
  for (const file of files) {
    if (!/\.(pdf|docx|txt|md|markdown)$/i.test(file.name)) return 'Choose PDF, DOCX, TXT or Markdown. Images use chat attachments.';
    if (!file.size || file.size > 8 * 1024 * 1024) return 'Choose nonempty documents up to 8 MB each.';
  }
  return files.reduce((sum, file) => sum + file.size, 0) > 20 * 1024 * 1024 ? 'Documents exceed the 20 MB batch limit.' : '';
}

export const documentPrompt = mode => mode === 'compare' ? 'Compare the selected documents, explaining similarities, differences and limitations with source citations.' : mode === 'summarize' ? 'Summarize the selected documents in full, citing sources and noting any extraction limitations.' : 'What are the key findings in the selected documents? Cite your sources.';
