-- Adiciona restrição de unicidade para evitar jobs duplicados para o mesmo alvo e tipo
-- Isto permite que o ON CONFLICT (target_id, task_type) funcione corretamente
ALTER TABLE ai_jobs ADD CONSTRAINT unique_target_task UNIQUE (target_id, task_type);
