FROM eclipse-temurin:21-jdk AS build
WORKDIR /app
COPY gradlew gradlew.bat ./
COPY gradle/wrapper gradle/wrapper
COPY build.gradle.kts settings.gradle.kts gradle.properties ./
RUN chmod +x gradlew && ./gradlew --version
COPY src ./src
RUN ./gradlew installDist --no-daemon --console=plain

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /app/build/install/instant-mechanic-dispatch ./dispatch
EXPOSE 8081
ENTRYPOINT ["./dispatch/bin/instant-mechanic-dispatch"]
