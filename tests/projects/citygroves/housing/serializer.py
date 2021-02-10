from housing.models import Room, Unit
from rest_framework import serializers


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = "__all__"


class RoomSerializer(serializers.ModelSerializer):
    unit = UnitSerializer()

    class Meta:
        model = Room
        fields = "__all__"
