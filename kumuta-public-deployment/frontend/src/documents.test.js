import assert from 'node:assert/strict';
import test from 'node:test';
import { validateDocuments, documentPrompt } from './documents.js';
test('Document uploads share batch limits and allow common document extensions', () => {
 const file = (name, size = 100) => ({ name, size });
 assert.equal(validateDocuments([file('A.PDF'), file('draft.docx'), file('note.txt'), file('readme.md')]), '');
 assert.match(validateDocuments([file('script.html')]), /Choose PDF/);
 assert.match(validateDocuments([file('empty.md', 0)]), /nonempty/);
 assert.match(validateDocuments(Array.from({length:6}, () => file('a.txt'))), /up to 5/);
 assert.match(validateDocuments(Array.from({length:3}, () => file('a.pdf', 8*1024*1024))), /20 MB/);
 assert.match(validateDocuments([file('a.pdf', 8*1024*1024+1)]), /8 MB/);
});
test('Whole-document prompts distinguish summaries and comparisons from passage questions', () => {
 assert.match(documentPrompt('summarize'), /in full/);
 assert.match(documentPrompt('compare'), /Compare/);
 assert.match(documentPrompt('search'), /Cite/);
});
