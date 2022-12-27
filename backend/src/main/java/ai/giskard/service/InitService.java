package ai.giskard.service;

import ai.giskard.domain.*;
import ai.giskard.domain.ml.Dataset;
import ai.giskard.domain.ml.ModelLanguage;
import ai.giskard.domain.ml.ProjectModel;
import ai.giskard.repository.ProjectRepository;
import ai.giskard.repository.RoleRepository;
import ai.giskard.repository.UserRepository;
import ai.giskard.repository.ml.DatasetRepository;
import ai.giskard.repository.ml.ModelRepository;
import ai.giskard.security.AuthoritiesConstants;
import ai.giskard.web.dto.DataUploadParamsDTO;
import ai.giskard.web.dto.ModelUploadParamsDTO;
import ai.giskard.web.dto.mapper.GiskardMapper;
import ai.giskard.web.dto.ml.DatasetDTO;
import ai.giskard.web.dto.ml.ModelDTO;
import ai.giskard.web.rest.errors.Entity;
import ai.giskard.web.rest.errors.EntityNotFoundException;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.google.common.collect.Sets;
import lombok.RequiredArgsConstructor;
import org.apache.commons.io.FileUtils;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.Assert;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import static java.util.Arrays.stream;

@Service
@RequiredArgsConstructor
public class InitService {

    private static final Map<String, FeatureType> germanCreditFeatureTypes = new HashMap<>();
    private static final Map<String, String> germanCreditColumnTypes = new HashMap<>();
    private static final Map<String, FeatureType> enronFeatureTypes = new HashMap<>();
    private static final Map<String, String> enronColumnTypes = new HashMap<>();
    private static final Map<String, FeatureType> zillowFeatureTypes = new HashMap<>();
    private static final Map<String, String> zillowColumnTypes = new HashMap<>();
    public static final String ZILLOW_PROJECT_KEY = "zillow";
    public static final String ENRON_PROJECT_KEY = "enron";
    public static final String GERMAN_CREDIT_PROJECT_KEY = "credit";
    private final UserRepository userRepository;
    private final RoleRepository roleRepository;
    private final ProjectRepository projectRepository;
    private final ProjectService projectService;
    private final GiskardMapper giskardMapper;
    private final PasswordEncoder passwordEncoder;
    private final Logger logger = LoggerFactory.getLogger(InitService.class);
    private final GeneralSettingsService generalSettingsService;
    private final FileLocationService fileLocationService;
    private Map<String, ProjectConfig> projects;
    String[] mockKeys = stream(AuthoritiesConstants.AUTHORITIES).map(key -> key.replace("ROLE_", "")).toArray(String[]::new);
    private final Map<String, String> users = stream(mockKeys).collect(Collectors.toMap(String::toLowerCase, String::toLowerCase));
    private final DatasetRepository datasetRepository;
    private final ModelRepository modelRepository;

    private Map<String, ProjectConfig> createProjectConfigMap() {
        return Map.of(
            ZILLOW_PROJECT_KEY, new ProjectConfig("House Pricing Regression", "aicreator",
                ModelUploadParamsDTO.builder().modelType("regression")
                    .projectKey(ZILLOW_PROJECT_KEY)
                    .name("House Pricing Model")
                    .language(ModelLanguage.PYTHON)
                    .languageVersion("3.7")
                    .featureNames(zillowFeatureTypes.keySet().stream().toList())
                    .build(),
                DataUploadParamsDTO.builder()
                    .projectKey(ZILLOW_PROJECT_KEY)
                    .name("House Pricing Data")
                    .featureTypes(zillowFeatureTypes)
                    .columnTypes(zillowColumnTypes)
                    .target("SalePrice")
                    .build(),
                new InspectionSettings()
            ),
            ENRON_PROJECT_KEY, new ProjectConfig("Email Classification", "aitester",
                ModelUploadParamsDTO.builder().modelType("classification")
                    .classificationLabels(List.of("CALIFORNIA CRISIS", "INFLUENCE", "INTERNAL", "REGULATION"))
                    .projectKey(ENRON_PROJECT_KEY)
                    .name("Email Classification Model")
                    .language(ModelLanguage.PYTHON)
                    .languageVersion("3.7")
                    .featureNames(enronFeatureTypes.keySet().stream().toList())
                    .build(),
                DataUploadParamsDTO.builder()
                    .name("Email data")
                    .featureTypes(enronFeatureTypes)
                    .columnTypes(enronColumnTypes)
                    .projectKey(ENRON_PROJECT_KEY)
                    .target("Target")
                    .build(),
                new InspectionSettings(5)
            ),
            GERMAN_CREDIT_PROJECT_KEY, new ProjectConfig("Credit Scoring Classification", "admin",
                ModelUploadParamsDTO.builder().modelType("classification")
                    .classificationLabels(List.of("Default", "Not default"))
                    .projectKey(GERMAN_CREDIT_PROJECT_KEY)
                    .name("Credit Scoring Model")
                    .language(ModelLanguage.PYTHON)
                    .languageVersion("3.7")
                    .featureNames(germanCreditFeatureTypes.keySet().stream().toList())
                    .build(),
                DataUploadParamsDTO.builder()
                    .name("Credit Scoring data")
                    .projectKey(GERMAN_CREDIT_PROJECT_KEY)
                    .target("default")
                    .featureTypes(germanCreditFeatureTypes)
                    .columnTypes(germanCreditColumnTypes)
                    .build(),
                new InspectionSettings()
            )
        );
    }

    public String getUserName(String key) {
        return users.get(key);
    }

    public String getProjectByCreatorLogin(String login) {
        return projects.entrySet().stream().filter(e -> e.getValue().creator.equals(login)).findFirst().orElseThrow().getValue().name;
    }

    /**
     * Initializing first authorities, mock users, and mock projects
     */
    @EventListener(ApplicationReadyEvent.class)
    @Transactional
    public void init() {
        projects = createProjectConfigMap();
        generalSettingsService.saveIfNotExists(new GeneralSettings());
        initAuthorities();
        initUsers();
        initProjects();
    }

    /**
     * Initialising users with different authorities
     */
    public void initUsers() {
        stream(mockKeys).forEach(key -> {
            if (userRepository.findOneByLogin(key.toLowerCase()).isEmpty()) {
                saveUser(key, "ROLE_" + key);
            }
        });
    }

    /**
     * Initiating authorities with AuthoritiesConstants values
     */
    public void initAuthorities() {
        stream(AuthoritiesConstants.AUTHORITIES).forEach(authName -> {
            if (roleRepository.findByName(authName).isPresent()) {
                logger.info("Authority {} already exists", authName);
                return;
            }
            Role role = new Role();
            role.setName(authName);

            roleRepository.save(role);

        });
    }

    /**
     * Registering the specified user
     *
     * @param key      key string used for identifying the user
     * @param roleName role given to the user
     */
    private void saveUser(String key, String roleName) {
        User user = new User();
        user.setLogin(key.toLowerCase());
        user.setEmail(String.format("%s@example.com", key.toLowerCase()));
        user.setActivated(true);
        Role role = roleRepository.findByName(roleName).orElseThrow(() -> new EntityNotFoundException(Entity.ROLE, roleName));
        user.setRoles(Sets.newHashSet(role));
        user.setPassword(passwordEncoder.encode(key.toLowerCase()));
        user.setEnabled(true);
        user.setActivated(true);
        userRepository.save(user);
    }

    /**
     * Initialized with default projects
     */
    public void initProjects() {
        logger.info("Creating demo projects");
        projects.forEach((key, config) -> {
            try {
                saveProject(key, config.creator);
            } catch (IOException e) {
                logger.error("Project with key %s not saved".formatted(key), e);
            }
        });
    }

    /**
     * Save project
     *
     * @param projectKey    project key used to easily identify the project
     * @param ownerUserName login of the owner
     */
    private void saveProject(String projectKey, String ownerUserName) throws IOException {
        if (projectRepository.findOneByKey(projectKey).isEmpty()) {
            String projectName = projects.get(projectKey).name;
            String ownerLogin = ownerUserName.toLowerCase();
            User owner = userRepository.getOneByLogin(ownerLogin);
            Assert.notNull(owner, "Owner does not exist in database");
            Project project = new Project(projectKey, projectName, projectName, owner);
            project.setMlWorkerType(MLWorkerType.INTERNAL);
            project.setInspectionSettings(projects.get(projectKey).inspectionSettings);
            projectService.create(project, ownerLogin);
            projectRepository.save(project);


            loadDatasets(project);
            loadModels(project);

            logger.info("Created project: {}", projectName);
        } else {
            logger.info("Project with key {} already exists", projectKey);
        }
    }

    private void loadDatasets(Project project) throws IOException {
        getArtifactResouceStream(project, "datasets").forEach(resource -> {
            try {
                saveDatasetResource(project, resource);
            } catch (IOException e) {
                logger.warn("Failed to save demo dataset {}", resource);
            }
        });
    }

    private void loadModels(Project project) throws IOException {
        getArtifactResouceStream(project, "models").forEach(resource -> {
            try {
                saveDModelResource(project, resource);
            } catch (IOException e) {
                logger.warn("Failed to save demo dataset {}", resource);
            }
        });
    }

    private Stream<Resource> getArtifactResouceStream(Project project, String artifactType) throws IOException {
        String path = "classpath:" + Paths.get("demo_projects", project.getKey(), artifactType, "*");

        PathMatchingResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
        return Arrays.stream(resolver.getResources(path)).filter(resource -> {
            try {
                return resource.getFile().isDirectory();
            } catch (IOException e) {
                logger.warn("Failed to read demo resource {}", resource.getFilename());
                return false;
            }
        });
    }

    private void saveDModelResource(Project project, Resource resource) throws IOException {
        Path metaPath = resource.getFile().toPath().resolve("giskard-model-meta.yaml");
        ObjectMapper mapper = new ObjectMapper(new YAMLFactory())
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        ModelDTO loadedMeta = mapper.readValue(Files.newInputStream(metaPath), ModelDTO.class);
        ProjectModel model = giskardMapper.fromDTO(loadedMeta);
        model.setProject(project);
        modelRepository.save(model);

        FileUtils.copyDirectory(resource.getFile().getParentFile(), fileLocationService.modelsDirectory(project.getKey()).toFile());
    }

    private void saveDatasetResource(Project project, Resource resource) throws IOException {
        Path metaPath = resource.getFile().toPath().resolve("giskard-dataset-meta.yaml");
        ObjectMapper mapper = new ObjectMapper(new YAMLFactory())
            .configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false);
        DatasetDTO loadedMeta = mapper.readValue(Files.newInputStream(metaPath), DatasetDTO.class);
        Dataset dataset = giskardMapper.fromDTO(loadedMeta);
        dataset.setProject(project);
        datasetRepository.save(dataset);

        FileUtils.copyDirectory(resource.getFile().getParentFile(), fileLocationService.datasetsDirectory(project.getKey()).toFile());
    }


    private record ProjectConfig(String name, String creator, ModelUploadParamsDTO modelParams,
                                 DataUploadParamsDTO datasetParams, InspectionSettings inspectionSettings) {
    }
}
