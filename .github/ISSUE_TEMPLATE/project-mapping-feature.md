---
name: "🔗 Add Reverse Project Mapping Feature"
about: Track projects associated with environment sets

---

**Is your feature request related to a problem? Please describe.**

Currently, `config.yaml` maintains the mapping from environment sets (e.g., `my_project_init_template`) to files that need to be synchronized. However, there is no mechanism to track which projects are using which environment sets. This creates several challenges:

- No visibility into which projects depend on a specific environment set
- Difficult to assess the impact of changes to templates
- Cannot easily update all affected projects when templates change
- No centralized view of project-to-configuration relationships

**Describe the solution you'd like**

Implement a new `project_mapping.yaml` file that maintains the reverse mapping - tracking which projects are associated with which environment sets. This file would:

1. Store project identifiers (paths or names) mapped to their active environment sets
2. Be automatically updated when projects initialize or change their environment sets
3. Provide a centralized view of all projects using the dotconfig-hub system
4. Enable bulk operations across projects using the same environment set

Example structure:
```yaml
projects:
  ~/workspace/my-python-app:
    environment_sets:
      - my_project_init_template
      - python_dev
    last_synced: 2024-01-15T10:30:00Z
  
  ~/workspace/frontend-project:
    environment_sets:
      - my_project_init_template
      - typescript_env
    last_synced: 2024-01-14T15:45:00Z
```

**Describe alternatives you've considered**

1. **Extending config.yaml**: Adding project mappings directly to `config.yaml`
   - Pros: Single file to manage
   - Cons: Mixes template definitions with usage tracking, making the file complex

2. **Local tracking only**: Store this information in each project's `dotconfig-hub.yaml`
   - Pros: Decentralized, no central file to manage
   - Cons: No global visibility, cannot perform bulk operations

3. **Database approach**: Use a lightweight database (SQLite) for tracking
   - Pros: Better querying capabilities
   - Cons: Adds complexity, requires additional dependencies