export const JOB_STAGES = ['queued','planning','generating','validating','rendering','completed'];
export const TERMINAL_JOBS = ['completed','failed','cancelled','timed_out'];
export function pendingJob(job) { return job && !TERMINAL_JOBS.includes(job.status); }
export function generationRequest(prompt, engine, artifactId, requestKey = crypto.randomUUID()) {
  return {request_key:requestKey,prompt,engine,...(artifactId?{artifact_id:artifactId}:{})};
}
export function generationLabel(status) {
  return {queued:'Queued',planning:'Planning structure',generating:'Generating content',validating:'Validating specification',rendering:'Preparing preview',completed:'Ready to preview',failed:'Generation failed',cancelled:'Cancelled',timed_out:'Timed out'}[status] || status;
}
