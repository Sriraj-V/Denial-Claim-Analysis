{#-
  Local drop-in of dbt_utils.generate_surrogate_key so this project builds even
  when `dbt deps` cannot reach the package hub. Behaviour is identical to
  dbt_utils: md5 of dash-joined, null-coalesced, cast-to-varchar fields.
  A project macro shadows the package macro, so this is safe to keep even after
  `dbt deps` installs dbt_utils.
-#}
{%- macro generate_surrogate_key(field_list) -%}
    {%- set default_null_value = "_dbt_utils_surrogate_key_null_" -%}
    {%- set fields = [] -%}
    {%- for field in field_list -%}
        {%- do fields.append(
            "coalesce(cast(" ~ field ~ " as varchar), '" ~ default_null_value ~ "')"
        ) -%}
        {%- if not loop.last %}
            {%- do fields.append("'-'") -%}
        {%- endif -%}
    {%- endfor -%}
    {{ dbt.hash(dbt.concat(fields)) }}
{%- endmacro -%}
