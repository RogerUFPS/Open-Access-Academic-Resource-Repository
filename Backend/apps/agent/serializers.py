from rest_framework import serializers


class AgentFilterSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    clave = serializers.CharField()
    nombre = serializers.CharField()
    tipo = serializers.CharField()
    valores_validos = serializers.ListField(
        child=serializers.CharField(), allow_null=True
    )
    formato = serializers.CharField(allow_null=True)


class AgentAreaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.CharField()


class AgentProgramSerializer(AgentAreaSerializer):
    areas = serializers.ListField(child=serializers.IntegerField())


class AgentSyntaxSerializer(serializers.Serializer):
    booleans = serializers.ListField(child=serializers.CharField())
    parenthesis = serializers.BooleanField()
    fields = serializers.DictField(child=serializers.CharField())


class AgentPlatformSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.CharField()
    idiomas = serializers.ListField(child=serializers.CharField())
    idioma_principal = serializers.CharField(allow_null=True)
    valid_sintaxis = AgentSyntaxSerializer(allow_null=True)


class AgentJournalSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    titulo = serializers.CharField()
    programas = serializers.ListField(child=serializers.IntegerField())
    plataformas = serializers.ListField(child=serializers.IntegerField())
    idiomas = serializers.ListField(child=serializers.CharField())
    tipos_documento = serializers.ListField(child=serializers.CharField())
    fecha_publicacion = serializers.DateField(allow_null=True)


class AgentSnapshotSerializer(serializers.Serializer):
    schema_version = serializers.IntegerField()
    programas = AgentProgramSerializer(many=True)
    areas = AgentAreaSerializer(many=True)
    filtros = AgentFilterSerializer(many=True)
    plataformas = AgentPlatformSerializer(many=True)
    revistas = AgentJournalSerializer(many=True)

