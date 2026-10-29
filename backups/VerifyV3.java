import org.flywaydb.core.Flyway;

class VerifyV3 {
    public static void main(String[] args) {
        var flyway = Flyway.configure()
            .dataSource(System.getenv("VERIFY_DB_URL"), System.getenv("VERIFY_DB_USER"), System.getenv("VERIFY_DB_PASSWORD"))
            .locations("filesystem:backend/banking-service/src/main/resources/db/migration")
            .defaultSchema("public").target("3").ignoreMigrationPatterns("*:pending").load();
        flyway.validate();
        flyway.migrate();
        flyway.validate();
        var version = flyway.info().current();
        if (version == null || !"3".equals(version.getVersion().toString())) {
            throw new IllegalStateException("Flyway version is not V3");
        }
        System.out.println("Verified Flyway V3 and migration checksums");
    }
}
